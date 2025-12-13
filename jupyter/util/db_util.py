import sqlite3
import pandas as pd
from util.conversion_util import Conversion
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
	
class Database:
	def __init__(self, db_path):
		self.db_path = db_path
		self.conn = sqlite3.connect(db_path)
		self.cursor = self.conn.cursor()
	
	def get_all_schools(self, year=2024):       
		query = "SELECT school.school_id, school_name, team_name, school_type, nickname, address, city, zip, \
		longitude, latitude, year, enrollment, school_classification, min_enrollment, max_enrollment \
		FROM school \
		INNER JOIN school_enrollment on school.school_id = school_enrollment.school_id and school_enrollment.year = ? \
		INNER JOIN school_classification ON school_enrollment.enrollment >= school_classification.min_enrollment AND \
		school_enrollment.enrollment <= school_classification.max_enrollment"
		
		parameters = (year, )
		df = pd.read_sql_query(query, self.conn, params=parameters)                                 
		return df
		
	def get_school_id(self, school_name):
		query = "SELECT school_id from school where school_name = ? or team_name = ?"
		parameters = (school_name, school_name)
		df = pd.read_sql_query(query, self.conn, params=parameters)
	
		if df.size == 0:
			return None
		else:
			return int(df.iloc[0,0])
	
	def get_all_house_values(self, year):
		query = "SELECT * from house_values where year = ?"
		parameters = (year, )
		df = pd.read_sql_query(query, self.conn, params=parameters)
		return df
		
	def get_meet_id(self, meet_type, meet_num, year, gender):
		query = "SELECT meet_id from meet where meet_type = ? and meet_num = ? and year = ? and gender = ?"
		parameters = (meet_type, meet_num, year, gender)
		df = pd.read_sql_query(query, self.conn, params=parameters)
		
		if df.size == 0:
			return None
		else:
			return int(df.iloc[0,0])

	def get_problem_athletes(self):
		query = "SELECT * from athlete where first = last and grad_year = 9999"
		df = pd.read_sql_query(query, self.conn)
		return df
		
	def get_athlete(self, athlete_id):
		query = "SELECT * from athlete where athlete_id = ?"
		parameters = (athlete_id, )
		df = pd.read_sql_query(query, self.conn, params=parameters)
		return df

	def get_athlete_id_wo_grad_year(self, first, last, school_id):
		query = "SELECT athlete_id from athlete where first like ? and last like ? and school_id = ? \
		  and grad_year != 9999"
		parameters = (f"%{first}%", f"%{last}%", school_id)
		df = pd.read_sql_query(query, self.conn, params=parameters)
		
		if df.size == 1:
			return int(df.iloc[0,0])
		else:
			return None
			
	def get_athlete_id(self, first, last, school_id, grad_year):
		query = "SELECT athlete_id from athlete where first = ? and last = ? and school_id = ? \
		  and grad_year = ? limit 1"
		parameters = (first, last, school_id, grad_year)
		df = pd.read_sql_query(query, self.conn, params=parameters)
		
		if df.size == 1:
			return int(df.iloc[0,0])
		else:
			return None
	
	def get_all_athlete_results(self):
		query = "select athlete_result.athlete_id, first, last, athlete.gender, event, result_type, grade, result, result2, place, school_name, enrollment, \
		school_type, nickname, host, meet_type, meet_num, meet.year, school.school_id, longitude, latitude \
		from athlete_result \
		inner join athlete on athlete_result.athlete_id = athlete.athlete_id \
		inner join school on athlete.school_id = school.school_id \
		inner join meet on meet.meet_id = athlete_result.meet_id \
		inner join school_enrollment on athlete.school_id = school_enrollment.school_id and meet.year = school_enrollment.year"
		df = pd.read_sql_query(query, self.conn)       
		return df
	
	def get_athlete_result(self, athlete_id, meet_id, event, result_type):
		query = "select * from athlete_result where athlete_id = ? and meet_id = ? and event = ? and result_type = ?"
		parameters = (athlete_id, meet_id, event, result_type)
		df = pd.read_sql_query(query, self.conn, params=parameters)       
		
		if df.size == 0:
			return None
		else:
			return int(df.iloc[0,0])
	
	def get_all_relay_results(self):
		query = "select school.school_id, event, result, result2, place, athlete_names, school_name, team_name, \
		school_type, host, meet_type, meet_num, gender, enrollment, meet.year \
		from relay_result \
		inner join school on relay_result.school_id = school.school_id \
		inner join meet on meet.meet_id = relay_result.meet_id \
		inner join school_enrollment on relay_result.school_id = school_enrollment.school_id \
		and meet.year = school_enrollment.year"
		df = pd.read_sql_query(query, self.conn)
		return df
	
	def get_relay_result(self, school_id, meet_id, event):
		query = "select * from relay_result where school_id = ? and meet_id = ? and event = ?"
		parameters = (school_id, meet_id, event)
		df = pd.read_sql_query(query, self.conn, params=parameters)       
		
		if df.size == 0:
			return None
		else:
			return int(df.iloc[0,0])
	
	def get_school_classifications(self):       
		query = "SELECT * from school_classification"
		df = pd.read_sql_query(query, self.conn)
		return df
	
	def get_tfrrs_info(self, year):
		query = "select * from tfrrs where year = ?"
		parameters = (year, )
		df = pd.read_sql_query(query, self.conn, params=parameters)     
		return df

	def merge_athlete(self, good_id, bad_id):
		query = "update athlete_result set athlete_id = ? where athlete_id = ?"
		parameters = (good_id, bad_id)
		self.cursor.execute(query, parameters)

		query = "update relay_athlete set athlete_id = ? where athlete_id = ?"
		self.cursor.execute(query, parameters)

		parameters = (bad_id, )
		query = "delete from athlete where athlete_id = ?"
		self.cursor.execute(query, parameters)
		
		self.conn.commit()
			
	def insert_meet(self, host, type, num, year, gender, commit=True):
		query = "INSERT INTO meet (host, meet_type, meet_num, year, gender) VALUES (?, ?, ?, ?, ?)"
		parameters = (host, type, num, year, gender)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
	
	def insert_school(self, name, team_name, type, nickname, address, city, zip, commit=True):
		query = "INSERT INTO school (school_name, team_name, school_type, nickname, address, city, zip) VALUES (?, ?, ?, ?, ?, ?, ?)"
		parameters = (name, team_name, type, nickname, address, city, zip)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
	
	def insert_school_enrollment(self, school_id, year, enrollment, commit=True):
		query = "INSERT OR IGNORE INTO school_enrollment (school_id, year, enrollment) VALUES (?, ?, ?)"
		parameters = (school_id, year, enrollment)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
		
	def insert_athlete(self, school_id, first, last, gender, grad_year, commit=True):
		query = "INSERT INTO athlete (school_id, first, last, gender, grad_year) VALUES (?, ?, ?, ?, ?)"
		parameters = (school_id, first, last, gender, grad_year)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
		
		# Return the autoincremented athlete_id for the inserted row - RTR add
		return self.cursor.lastrowid
	
	def insert_athlete_result(self, athlete_id, meet_id, event, type, grade, result, result2, place, commit=True):
		query = "INSERT INTO athlete_result (athlete_id, meet_id, event, result_type, grade, result, result2, place) \
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
		parameters = (athlete_id, meet_id, event, type, grade, result, result2, place)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
	
	def insert_relay_result(self, school_id, meet_id, event, result, result2, place, athlete_names, commit=True):
		query = "INSERT INTO relay_result (school_id, meet_id, event, result, result2, place, athlete_names) \
		VALUES (?, ?, ?, ?, ?, ?, ?)"
		parameters = (school_id, meet_id, event, result, result2, place, athlete_names)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
		
		# Return the autoincremented relay_id for the inserted row - RTR add
		return self.cursor.lastrowid

	# RTR add
	def insert_relay_athlete(self, relay_id, athlete_id, commit=True):
		query = "INSERT INTO relay_athlete (relay_id, athlete_id) \
		VALUES (?, ?)"
		parameters = (relay_id, athlete_id)
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
	
	def insert_tfrrs(self, year, gender, meet_type, link_id, increment, commit=True):
		query = "INSERT OR IGNORE INTO tfrrs (year, gender, meet_type, link_id, increment) \
		VALUES (?, ?, ?, ?, ?)"
		parameters = (year, gender, meet_type, link_id, increment)
		
		self.cursor.execute(query, parameters)

		if commit:
			self.conn.commit()
	
	def get_top_results_from_meet(self, top_num, meet, result_type, low, high):
		query = "select first, last, athlete.gender, event, grade, result, result2, place, school.school_name, enrollment, \
		school.school_type, nickname, host, meet_type, meet_num, meet.year, meet.gender, athlete.school_id \
		from athlete_result \
		inner join athlete on athlete_result.athlete_id = athlete.athlete_id \
		inner join school on athlete.school_id = school.school_id \
		inner join meet on meet.meet_id = athlete_result.meet_id \
		inner join school_enrollment on athlete.school_id = school_enrollment.school_id and meet.year = school_enrollment.year \
		where meet.meet_id = ? and athlete_result.place <= ? and athlete_result.result_type = ? and enrollment >= ? and enrollment <= ?"
		parameters = (meet, top_num, result_type, low, high)
		df = pd.read_sql_query(query, self.conn, params = parameters)       
		return df
	
	def get_top_relays_from_meet(self, top_num, meet, low, high):
		query = "select relay_result.school_id, event, result, result2, place, enrollment, athlete_names, school.school_name, school.team_name, \
		school.school_type, meet.meet_type, meet.meet_num, meet.gender, meet.year \
		from relay_result \
		inner join school on relay_result.school_id = school.school_id \
		inner join meet on meet.meet_id = relay_result.meet_id\
		inner join school_enrollment on relay_result.school_id = school_enrollment.school_id and meet.year = school_enrollment.year \
		where meet.meet_id = ? and relay_result.place <= ? and enrollment >= ? and enrollment <= ?"
		parameters = (meet, top_num, low, high)
		df = pd.read_sql_query(query, self.conn, params = parameters)
		df.columns = ('school_id', 'event', 'result', 'result2', 'place', 'enrollment', 'athlete_names', 'school_name', 'team_name', \
		'school_type', 'meet_type', 'meet_num', 'gender', 'year')
		return df
	
	def get_school_name(self, school_id):
		query = "SELECT school_name from school where school_id = ?"
		parameters = (school_id,)
		df = pd.read_sql_query(query, self.conn, params=parameters)
	
		if df.size == 0:
			return None
		else:
			return df.iloc[0,0]
	
	def get_latitude(self, school_id):
		query = "SELECT latitude FROM school where school_id = ?"
		parameters = (school_id, )
		df = pd.read_sql_query(query, self.conn, params=parameters)
	
		if df.size == 0:
			return None
		else:
			return float(df.iloc[0,0])
		
	def get_longitude(self, school_id):
		# get longitude
		query = "SELECT longitude FROM school where school_id = ?"
		parameters = (school_id, )
		df = pd.read_sql_query(query, self.conn, params=parameters)
		
		if df.size == 0:
			return None
		else:
			return float(df.iloc[0,0])
			
	def get_state_standard(self, year, gender, event):

		# group events for later processing
		prelim_event = ["100 Meters", "200 Meters", "100 Hurdles", "110 Hurdles"]
		round_down_whole = ["Discus", "High Jump"] # round down to whole inch
		round_down_quarter = ["Long Jump", "Shot Put"] # round down to nearest quarter inch

		# how many years to average
		YEARS = 3

		# maintain sum
		sum = 0

		# TEMPORARY

		c = Conversion()

		if gender == "Boys":
			if event == "4 x 800 Relay":
			    sum = sum + c.time_to_seconds("7:55.19")
			elif event == "110 Hurdles":
			    sum = sum + c.time_to_seconds("14.85")
			elif event == "100 Meters":
			    sum = sum + c.time_to_seconds("10.82")
			elif event == "1600 Meters":
			    sum = sum + c.time_to_seconds("4:15.87")
			elif event == "4 x 100 Relay":
			    sum = sum + c.time_to_seconds("42.45")
			elif event == "400 Meters":
			    sum = sum + c.time_to_seconds("49.19")
			elif event == "300 Hurdles":
			    sum = sum + c.time_to_seconds("39.47")
			elif event == "800 Meters":
			    sum = sum + c.time_to_seconds("1:54.84")
			elif event == "200 Meters":
			    sum = sum + c.time_to_seconds("21.98")
			elif event == "3200 Meters":
			    sum = sum + c.time_to_seconds("9:11.71")
			elif event == "4 x 400 Relay":
			    sum = sum + c.time_to_seconds("3:21.56")
			elif event == "Discus":
			    sum = sum + c.distance_to_inches("158' 9\"")
			elif event == "Shot Put":
			    sum = sum + c.distance_to_inches("57' 4.5\"")
			elif event == "Long Jump":
			    sum = sum + c.distance_to_inches("22' 2\"")
			elif event == "High Jump":
			    sum = sum + c.distance_to_inches("6' 4\"")
			elif event == "Pole Vault":
			    sum = sum + c.distance_to_inches("14' 0\"")
		else:
			if event == "4 x 800 Relay":
				sum = sum + c.time_to_seconds("9:25.87")
			elif event == "100 Hurdles":
				sum = sum + c.time_to_seconds("14.54")
			elif event == "100 Meters":
				sum = sum + c.time_to_seconds("12.17")
			elif event == "1600 Meters":
				sum = sum + c.time_to_seconds("5:01.10")
			elif event == "4 x 100 Relay":
				sum = sum + c.time_to_seconds("48.52")
			elif event == "400 Meters":
				sum = sum + c.time_to_seconds("57.79")
			elif event == "300 Hurdles":
				sum = sum + c.time_to_seconds("45.43")
			elif event == "800 Meters":
				sum = sum + c.time_to_seconds("2:16.09")
			elif event == "200 Meters":
				sum = sum + c.time_to_seconds("25.37")
			elif event == "3200 Meters":
				sum = sum + c.time_to_seconds("10:47.35")
			elif event == "4 x 400 Relay":
				sum = sum + c.time_to_seconds("3:59.08")
			elif event == "Discus":
				sum = sum + c.distance_to_inches("125' 7\"")
			elif event == "Shot Put":
				sum = sum + c.distance_to_inches("41' 2.5\"")
			elif event == "Long Jump":
				sum = sum + c.distance_to_inches("18' 2.25\"")
			elif event == "High Jump":
				sum = sum + c.distance_to_inches("5' 4\"")
			elif event == "Pole Vault":
				sum = sum + c.distance_to_inches("11' 3\"")
		
		if "Relay" in event:
			for n in range(YEARS):
				year = year - 1

				# temporary
				if year == 2022:
					continue
				
				query = "SELECT result2 FROM relay_result \
				inner join meet on relay_result.meet_id = meet.meet_id \
				where meet_type = 'State' and place = 9 and gender = ? and event = ? and year = ?"

				parameters = (gender, event, year)
				df = pd.read_sql_query(query, self.conn, params=parameters)
				avg = df.iloc[0,0]

				if df.iloc[0,0] != None:
					sum = sum + df.iloc[0,0]
			
		else:
			
			# determine result type to use
			if event in prelim_event:
				result_type = "Prelim"
			else:
				result_type = "Final"
			
			for n in range(YEARS):
				year = year - 1

				# temporary
				if year == 2022:
					continue
				
				# get the highest place within the top 9 -- this is necessary due to possible ties
				query = "SELECT MAX(place) FROM athlete_result \
				inner join meet on athlete_result.meet_id = meet.meet_id \
				where result_type = ? and meet_type = 'State' and gender = ? and event = ? and year = ? and place <= 9"

				parameters = (result_type, gender, event, year)
				df = pd.read_sql_query(query, self.conn, params=parameters)
				
				if df.iloc[0,0] != None:
					place = int(df.iloc[0,0])
				else:
					place = 9
				
				# limit results to 1 returned row per query, in case of ties
				query2 = "SELECT result2 FROM athlete_result \
				inner join meet on athlete_result.meet_id = meet.meet_id \
				where result_type = ? and meet_type = 'State' and place = ? and gender = ? and event = ? and year = ? limit 1"
				
				parameters2 = (result_type, place, gender, event, year)
				df2 = pd.read_sql_query(query2, self.conn, params=parameters2)

				if df2.iloc[0,0] != None:
					sum = sum + df2.iloc[0,0]

		# calculate the average
		avg = sum / YEARS
		
		# round Pole Vault down to quarter feet; inch increments are 0", 3", 6", 9"
		if event == "Pole Vault":
			feet = avg / 12
			rounded_to_feet_quarters = (Decimal(feet) * 4).to_integral_value(rounding=ROUND_DOWN) / 4
			return 12 * rounded_to_feet_quarters

		# round these events down to nearest whole number
		elif event in round_down_whole:
			return Decimal(avg).quantize(Decimal("1"), rounding=ROUND_DOWN)
		
		# round these events down to nearest quarter quarter inch
		elif event in round_down_quarter:
			return (Decimal(avg) * 4).to_integral_value(rounding=ROUND_DOWN) / 4

		# normal rounding to the hundreds place
		else:		
			return Decimal(str(avg)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

	def get_event_type(self, event):
		query = "SELECT event_type from event where event = ?"
		parameters = (event,)
		df = pd.read_sql_query(query, self.conn, params=parameters)
	
		if df.size == 0:
			return None
		else:
			return df.iloc[0,0] 

	def do_commit(self):
		self.conn.commit()