import pandas as pd
import numpy as np
import datetime
import json

import matplotlib.pyplot as plt
from subprocess import check_output
# http://geophysics.eas.gatech.edu/people/zpeng/Software/sac_msc/

from obspy.geodetics import gps2dist_azimuth
from obspy.geodetics import locations2degrees

def cell_fn(i,j,k, lb_corner, phase_info, station_info, tt, DX, DZ, TT_DX, TT_DZ, TT_NX, find_station_misfit = False, ref_mean = 0, ref_origin = 0):
	cell_coords = [i * DX + lb_corner[0], j * DX + lb_corner[1], k * DZ]

	delta_r = [] # distance and depth pairs
	phase_list = []

	#obs_tt = []

	arrivals = [] # origin times
	_station_list = []
	# this only uses phases chosen by REAL association

	for station in phase_info:

		for phase in ["station_P", "station_S"]:
			if phase not in phase_info[station]:
				continue

			_dep = k * DZ # stations assumed to be at 0 km elevation

			_dist = dx([station_info[station]["lon"], station_info[station]["lat"]], cell_coords[:2])

			_row = [_dist, _dep]
			delta_r.append(_row)

			if phase == "station_P":
				phase_list.append("P")
				
			elif phase == "station_S":
				phase_list.append("S")

			arrivals.append(phase_info[station][phase])

			# if do_mc:
			# 	mc_delta = np.random.normal(0, scale = mc_args["sigma_ml"])
			# else:
			# 	mc_delta = 0

			_station_list.append(station)

			#print(_row)

	delta_r = np.array(delta_r)
	#obs_tt = np.array(obs_tt)

	# bin the distance and depth 
	# bin distance only (?) i won't be touching depth
	# 
	# the travel time table is defined in kilometres, but the dx function
	# returns kilometres, so this is fine....
	# 
	
	tt_dist_indices = np.array([int(round(x)) for x in delta_r[:, 0]/TT_DX]) # for table interpolation

	
	# TT_DX is 1 so this is ok
	tt_dist_deltas = delta_r[:,0] - tt_dist_indices * TT_DX

	tt_dep_index = int(round((k * DZ)/TT_DZ))

	# print("indices", tt_dist_indices[:5])
	# print("actual", delta_r[:5,0])
	# print("deltas", tt_dist_deltas[:5])
	#print(tt_dep_index)

	#print(max(delta_r[:,0]))

	#print(tt_dist_indices)
	#print(tt_dist_deltas)
	#
	
	tt_cell = []
	
	tt_dist_gradients = []


	# do an interpolation operation by taking the nearby indices
	# and estimating gradient

	for _c, _i in enumerate(tt_dist_indices): #_i are for travel time table indices

		if _i + 1 > TT_NX:
			_indices = np.array([_i - 1, _i])
		elif _i - 1 < 0:
			_indices = np.array([_i, _i + 1])
		else:
			_indices = np.array([_i - 1, _i, _i + 1]) 

		if phase_list[_c] == "P":
			_Y = [tt[_x][tt_dep_index][0] for _x in _indices]
			tt_cell.append(tt[_i][tt_dep_index][0])

		elif phase_list[_c] == "S":
			_Y = [tt[_x][tt_dep_index][1] for _x in _indices]

			tt_cell.append(tt[_i][tt_dep_index][1])

		tt_dist_gradients.append(ip((_indices) * TT_DX, _Y))

	tt_dist_gradients = np.array(tt_dist_gradients)
	tt_cell = np.array(tt_cell)

	#print("without correction", tt_cell[:5])

	# add the correction from the table terms using interpolation method

	tt_cell += tt_dist_gradients * tt_dist_deltas

	#print("w corr", tt_cell[:5])

	# with the travel times, find the set of origin times

	assert len(phase_list) == len(arrivals) == len(tt_cell)

	guess_ot = []

	for _c in range(len(arrivals)):
		guess_ot.append(arrivals[_c] - datetime.timedelta(seconds = tt_cell[_c]))

	# normalise the origin times and find the std 

	min_origin_time = min(guess_ot)
	for _c in range(len(guess_ot)):
		guess_ot[_c] = (guess_ot[_c] - min_origin_time).total_seconds()

	mean_time = np.mean(guess_ot)
	std_time = np.std(guess_ot)


	# SAVE the misfits on a per station basis (currently it's just summed )
	# save it somewhere (json)

	# instead of taking the mean i should be trying to minimise the residuals
	# 
	# 
	#ref_str = datetime.datetime.strftime(min_origin_time, "%Y%m%d-%H%M%S.%f")
	#
	 
	if find_station_misfit:
		# find the squared deltas between the mean times and the observation times

		station_misfit = {}
		for _i in range(len(_station_list)):
			_sta = _station_list[_i]

			if _sta not in station_misfit:
				station_misfit[_sta] = {}

			_phase = phase_list[_i]

			station_misfit[_sta][_phase] = np.abs((min_origin_time + datetime.timedelta(seconds = guess_ot[_i] - ref_mean) - datetime.datetime.fromtimestamp(ref_origin)).total_seconds())

		print(station_misfit)
		return station_misfit

	else:
		return (std_time, mean_time, min_origin_time.timestamp())



def arbitrary_search(args, lb_corner, grid_length, phase_info, station_info, tt, get_grid = False):

	# pass in an arbitrary lower left corner, along with the size of the box

	print("lb_corner", lb_corner, "grid_length", grid_length)


	N_Z = args["N_Z"]
	
	DZ = args["DZ"]
	
	TT_DX = args["TT_DX"]
	TT_DZ = args["TT_DZ"]
	TT_NX = args["TT_NX"]
	TT_NZ = args["TT_NZ"]


	# arbitrary_search (call itself)

	# 111km --> 1 degree
	# 0.3 km --> 
	# 
	
	# grid_length is in units of decimal degrees

	DX = grid_length / (args["N_DX"])
	args["DX"] = DX	

	# if do_mc:
	# 	mc_mask = np.zeros([args["N_DX"]+1, args["N_DX"]+1, N_Z])


	grid = np.zeros([args["N_DX"] + 1, args["N_DX"] + 1, N_Z, 3])

	for i in range(args["N_DX"] + 1): # lon
	#for i in range(1):
	#	for j in range(1):
		for j in range(args["N_DX"] + 1): # lat
			for k in range(N_Z): # depth

				_cell_output = cell_fn(i, j, k, lb_corner, phase_info, station_info, tt, DX, DZ, TT_DX, TT_DZ, TT_NX)
			
				grid[i][j][k][:] = _cell_output

				
	L2 = grid[:,:,:,0] # 0: get the standard deviation

	indices = np.where(L2 == L2.min())

	#print(indices)


	best_i = indices[0][0]
	best_j = indices[1][0]
	best_k = indices[2][0]


	best_x = lb_corner[0] + best_i * args["DX"]
	best_y = lb_corner[1] + best_j * args["DX"]
	best_z = best_k * args["DZ"]



	output = {
		"best_x": best_x,		
		"best_y": best_y,
		"best_z": best_z,
		"sigma_ml":  grid[best_i, best_j, best_k, 0],
		"mean_time": grid[best_i, best_j, best_k, 1],
		"ref_time":  grid[best_i, best_j, best_k, 2],
		"ref_timestamp":  datetime.datetime.strftime(datetime.datetime.fromtimestamp(grid[best_i, best_j, best_k, 2]), "%Y%m%d-%H%M%S.%f"),
	}

	print(output)

	# get station misfits if it's the minimum

	if get_grid:
		station_misfit = cell_fn(best_i,best_j,best_k, lb_corner, phase_info, station_info, tt, DX, DZ, TT_DX, TT_DZ, TT_NX, find_station_misfit = True, ref_mean = grid[best_i, best_j, best_k, 1], ref_origin = grid[best_i, best_j, best_k, 2])

		return (grid, station_misfit, lb_corner, DX, args["N_DX"] + 1)


	# positions:

	# centre around the minimum point, take +/- 2 indices
	# for an initial N of 20, this means that you will pass 4 points 
	# 
	# i also realise that like i have fence post problem . . . .actually maybe not because i'm rounding up my gridlength
	# 
	# 
	
	# find new lower left corner:

	new_lb_corner = (best_x - 2 * DX, best_y - 2 * DX)
	new_grid_length = DX * 4

	new_DX = new_grid_length / args["N_DX"]
		
	if DX < (0.1/111.11): # pretty arbitrary / could make it a flag
		return output
	else:
		return arbitrary_search(args, new_lb_corner, new_grid_length, phase_info, station_info, tt)


def dx(X1, X2):
	"""
	
	takes in two coordinate tuples (lon, lat), (lon, lat) returning their distance in kilometres
	gps2dist_azimuth also returns the azimuth but i guess i don't need that yet
	it also returns distances in metres so i just divide by 1000

	the order doesn't matter
	
	:param      X1:   The x 1
	:type       X1:   { type_description }
	:param      X2:   The x 2
	:type       X2:   { type_description }

	"""

	#print(X1, X2)
	return gps2dist_azimuth(X1[1], X1[0], X2[1], X2[0])[0] / 1000

	# out = check_output(["./gridsearch/distbaz", "{:.7g}".format(X1[0]), "{:.7g}".format(X1[1]), "{:.7g}".format(X2[0]), "{:.7g}".format(X2[1])])
	# #print(out)
	# out = [float(x) for x in out.decode('UTF-8').strip().split(" ") if x != ""]
	# #print(out[0])
	# return out[0]


def ip(X, Y):
	if len(X) == 3:

		# arithmetic average of in between gradients to approximate gradient at midpoint

		return 0.5 * ((Y[2] - Y[1])/(X[2] - X[1]) + (Y[1] - Y[0])/(X[1] - X[0]))

	if len(X) == 2:

		return (Y[1] - Y[0])/(X[1] - X[0])



"""
# save the mean and std origin time in the grid
					# saving the datetime object sounds like a bad idea
					# so just convert the reference time to a string?
					# so it'll be
					# 
					# std
					# mean delta
					# min_time reference as string
					# 
					# then i can look up the cell, and reobtain the mean time
					# 
					
					following code was done assuming the truth of REAL travel times, which
					may not always be the case
					they are left here for reference

					# # calculate L2 and L1 errors

					# sq_residuals = (tt_cell - obs_tt)**2
					# abs_residuals = np.sqrt(sq_residuals)

					# # keep standard dev in array because idk that could be useful? 

					# volume = (grid_length * DX)**2 * (Z_RANGE)

					# sq_residuals /= volume
					# abs_residuals /= volume

					# L2 = np.sum(sq_residuals)
					# L2_std = np.std(sq_residuals)
					# L1 = np.sum(abs_residuals)
					# L1_std = np.std(abs_residuals)

					# grid[i][j][k][0] = L2
					# grid[i][j][k][1] = L2_std
					# grid[i][j][k][2] = L1
					# grid[i][j][k][3] = L1_std

"""



	