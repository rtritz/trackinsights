import pandas as pd

class Conversion:

	def time_to_seconds(self, time):
		if time.isalpha():
			return 9999
	
		if time[len(time)-1] == 'h':
			time = time[0:len(time)-1]
	
		colon_index = time.find(":")
		if colon_index == -1:
			return float(time)
	
		min = int(time[0: colon_index])
		sec = float(time[colon_index+1:])
	
		return round(min * 60 + sec, 2)
	
	def distance_to_inches(self, distance):
		if distance.isalpha():
			return 0
	
		distance = distance.replace("\"", "")
		index = distance.find("'")
		
		if index == -1:
			return float(distance)
			
		feet = int(distance[0:index])
		inches = float(distance[index+1:])
		
		return feet * 12 + inches
	
	def inches_to_distance(self, total_inches):
		feet = total_inches // 12
		inches = total_inches % 12
		
		# is whole number?
		if inches == inches.to_integral_value():
			inches_str = f"{int(inches)}\""
		else:
			inches_str = f"{inches:.2f}\"".rstrip('0').rstrip('.') # remove trailing 0's and decimals if present
		
		return f"{int(feet)}' {inches_str}"
	
	def seconds_to_time(self, total_seconds):
		minutes = int(total_seconds) // 60
		seconds = total_seconds % 60

		# is whole number?
		if seconds == seconds.to_integral_value():
			seconds_str = f"{int(seconds)}"  
		else:
			seconds_str = f"{seconds:.2f}"
		
		if minutes == 0:
			return f"{seconds_str}"
		else:
			return f"{minutes}:{seconds_str}"
	
	
