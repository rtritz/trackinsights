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
	
	def get_athlete_id(self, first, last, school_id):
		query = "SELECT athlete_id from athlete where first = ? and last = ? and school_id = ?"
		parameters = (first, last, school_id)
		df = pd.read_sql_query(query, self.conn, params=parameters)
		
		if df.size == 0:
			return None
		else:
			return int(df.iloc[0,0])
	
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
		
	def insert_meet(self, host, type, num, year, gender):
		query = "INSERT INTO meet (host, meet_type, meet_num, year, gender) VALUES (?, ?, ?, ?, ?)"
		parameters = (host, type, num, year, gender)
		self.cursor.execute(query, parameters)
		self.conn.commit()
	
	def insert_school(self, name, team_name, type, nickname, address, city, zip):
		query = "INSERT INTO school (school_name, team_name, school_type, nickname, address, city, zip) VALUES (?, ?, ?, ?, ?, ?, ?)"
		parameters = (name, team_name, type, nickname, address, city, zip)
		self.cursor.execute(query, parameters)
		self.conn.commit()
	
	def insert_school_enrollment(self, school_id, year, enrollment):
		query = "INSERT OR IGNORE INTO school_enrollment (school_id, year, enrollment) VALUES (?, ?, ?)"
		parameters = (school_id, year, enrollment)
		self.cursor.execute(query, parameters)
		self.conn.commit()
		
	def insert_athlete(self, school_id, first, last, gender):
		query = "INSERT INTO athlete (school_id, first, last, gender) VALUES (?, ?, ?, ?)"
		parameters = (school_id, first, last, gender)
		self.cursor.execute(query, parameters)
		self.conn.commit()
	
	def insert_athlete_result(self, athlete_id, meet_id, event, type, grade, result, result2, place):
		query = "INSERT INTO athlete_result (athlete_id, meet_id, event, result_type, grade, result, result2, place) \
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
		parameters = (athlete_id, meet_id, event, type, grade, result, result2, place)
		self.cursor.execute(query, parameters)
		self.conn.commit()
	
	def insert_relay_result(self, school_id, meet_id, event, result, result2, place, athlete_names):
		query = "INSERT INTO relay_result (school_id, meet_id, event, result, result2, place, athlete_names) \
		VALUES (?, ?, ?, ?, ?, ?, ?)"
		parameters = (school_id, meet_id, event, result, result2, place, athlete_names)
		self.cursor.execute(query, parameters)
		self.conn.commit()
	
	def insert_tfrrs(self, year, gender, meet_type, link_id, increment):
		query = "INSERT OR IGNORE INTO tfrrs (year, gender, meet_type, link_id, increment) \
		VALUES (?, ?, ?, ?, ?)"
		parameters = (year, gender, meet_type, link_id, increment)
		
		self.cursor.execute(query, parameters)
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
			
	def get_event_type(self, event):
		query = "SELECT event_type from event where event = ?"
		parameters = (event,)
		df = pd.read_sql_query(query, self.conn, params=parameters)
	
		if df.size == 0:
			return None
		else:
			return df.iloc[0,0] 
