class CONST:
	"""A class to store application constants with IntelliSense support."""

	class GENDER:
		BOYS = "Boys"
		GIRLS = "Girls"
		ALL = [BOYS, GIRLS]

	class MEET_TYPE:
		SECTIONAL = "Sectional"
		REGIONAL = "Regional"
		STATE = "State"
		ALL = [SECTIONAL, REGIONAL, STATE]

	class RESULT_TYPE:
		PRELIM = "Prelim"
		FINAL = "Final"
		ALL = [PRELIM, FINAL]

	class EVENT_TYPE:
		PRELIM = "Prelim"
		HURDLE = "Hurdle"
		RELAY = "Relay"
		FIELD = "Field"
		TRACK = "Track"
				
	class EVENT:
		# Track
		E100 = "100 Meters"
		E200 = "200 Meters"
		E400 = "400 Meters"
		E800 = "800 Meters"
		E1600 = "1600 Meters"
		E3200 = "3200 Meters"
		ALL_TRACK = [E100, E200, E400, E800, E1600, E3200]
		
		# Hurdles 
		E100H = "100 Hurdles"
		E110H = "110 Hurdles"
		E300H = "300 Hurdles"
		ALL_GIRLS_HURDLES = [E100H, E300H]
		ALL_BOYS_HURDLES = [E110H, E300H]
		
		# Field
		EHJ = "High Jump"
		ELJ = "Long Jump"
		ESP = "Shot Put"
		EDT = "Discus"
		EPV = "Pole Vault"
		ALL_FIELD = [EHJ, ELJ, ESP, EDT, EPV]
		
		# Relay
		E400R = "4 x 100 Relay"
		E1600R = "4 x 400 Relay"
		E3200R = "4 x 800 Relay"
		ALL_RELAY = [E400R, E1600R, E3200R]

		ALL_GIRLS_PRELIM = [E100, E200, E100H]
		ALL_BOYS_PRELIM = [E100, E200, E110H]
		ALL_GIRLS_EVENTS = [ALL_TRACK, ALL_FIELD, ALL_RELAY, ALL_GIRLS_HURDLES]
		ALL_BOYS_EVENTS = [ALL_TRACK, ALL_FIELD, ALL_RELAY, ALL_BOYS_HURDLES]
		
	# File paths
	DB_PATH = "./db/Track.db"
	OUTPUT_PATH = "./output"