import requests
import json 
import pandas as pd 
import time
from json_flatten import flatten
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
import os 

load_dotenv()

OW_api_key = os.getenv('OW_api_key')
db_name = os.getenv('db_name')
db_user = os.getenv('user')
db_pass = os.getenv('password')
db_host = os.getenv('host')
db_port = os.getenv('port')

#Load data containing cities for the API
json_save_path = rf'Final_city_data.json'
with open(json_save_path) as f:
    city_data = json.load(f)

#Weather and Pollution API requests
OW_weather_data = []
OW_pollution_data = []
delay = 2
units = "metric"
for city in city_data:

     #Load the longitude and latitude data for each city
     lat = city['latitude']
     lon = city['longitude']
     city_id = city['city_id']

     #Fetch the current weather data 
     OW_weather_url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units={units}&appid={OW_api_key}'
     response_weather = requests.get(OW_weather_url)
     weather_data = response_weather.json()
     weather_data['latitude'] = lat
     weather_data['longitude'] = lon
     weather_data['city_id'] = city_id
     OW_weather_data.append(weather_data)
     time.sleep(delay)

     #Fetch the current air quality data
     OW_pollution_url = f'http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&units={units}&appid={OW_api_key}'
     response_pollution = requests.get(OW_pollution_url)
     pollution_data = response_pollution.json()
     pollution_data['latitude'] = lat
     pollution_data['longitude'] = lon
     pollution_data['city_id'] = city_id
     OW_pollution_data.append(pollution_data)
     time.sleep(delay)

#Function for handling column names and datatypes
def rename_and_convert_columns(df, column_map):
    """
    Renames columns in a DataFrame and converts them to the specified data types.

    Args:
        df (pd.DataFrame): The DataFrame to process.
        column_map (dict): A dictionary where keys are original column names and values are tuples of 
                           the new column name and data type (e.g., ('new_name', 'dtype')).

    Returns:
        pd.DataFrame: The modified DataFrame with renamed columns and converted data types.
    """
    for original_col, (new_col, dtype) in column_map.items():
        if original_col in df.columns:
            df.rename(columns={original_col: new_col}, inplace=True)
            
            # Convert to appropriate data type
            if dtype == 'float':
                df[new_col] = pd.to_numeric(df[new_col], errors='coerce')
            elif dtype == 'int':
                df[new_col] = pd.to_numeric(df[new_col], errors='coerce', downcast='integer')
            elif dtype == 'datetime':
                # Explicitly cast to numeric before converting to datetime
                df[new_col] = pd.to_datetime(pd.to_numeric(df[new_col], errors='coerce'), unit='s', errors='coerce')
                df[new_col] = df[new_col].dt.round('min')
    return df


def calculate_local_time(datetime_str, lat, lon):
    """
    Calculates the local time based on latitude, longitude, and UK local datetime.

    Parameters:
    datetime_str (str): The datetime in UK local time as a string.
    lat (float): Latitude of the location.
    lon (float): Longitude of the location.

    Returns:
    pd.Timestamp: The local time as a Pandas Timestamp object.
    """
  
    # Parse the UK local datetime string into a datetime object
    uk_datetime = pd.to_datetime(datetime_str)

    # Initialize TimezoneFinder
    tf = TimezoneFinder()

    # Find timezone based on latitude and longitude
    timezone_str = tf.timezone_at(lng=lon, lat=lat)

    # Get the timezone
    timezone = pytz.timezone(timezone_str)
    # Convert the UK local time to local time in the identified timezone
    local_time = pd.Timestamp(uk_datetime).tz_localize(pytz.timezone('Europe/London')).astimezone(timezone)
    return local_time.tz_localize(None)

# Change the column names, format and dtypes for the weather data 
flattened_weather_data = [flatten(item) for item in OW_weather_data]
weather_data_df = pd.DataFrame(flattened_weather_data)

        # Define a mapping for column renaming and data type conversions
weather_column_map = {
    'city_id$int': ('city_id', 'int'),
    'longitude$float': ('longitude', 'float'),
    'latitude$float': ('latitude', 'float'),
    'weather.[0].id$int': ('weather_id', 'int'),
    'weather.[0].main': ('weather_main', 'str'),
    'weather.[0].description': ('weather_description', 'str'),
    'weather.[0].icon': ('weather_icon', 'str'),
    'main.temp$float': ('temperature', 'float'),
    'main.feels_like$float': ('feels_like', 'float'),
    'main.temp_min$float': ('temp_min', 'float'),
    'main.temp_max$float': ('temp_max', 'float'),
    'main.pressure$int': ('pressure', 'int'),
    'main.humidity$int': ('humidity', 'int'),
    'main.sea_level$int': ('sea_level', 'int'),
    'main.grnd_level$int': ('grnd_level', 'int'),
    'visibility$int': ('visibility', 'int'),
    'wind.speed$float': ('wind_speed', 'float'),
    'wind.deg$int': ('wind_deg', 'int'),
    'clouds.all$int': ('clouds_all', 'int'),
    'dt$int': ('date_time', 'datetime'),
    'sys.type$int': ('sys_type', 'int'),
    'sys.id$int': ('sys_id', 'int'),
    'sys.country': ('sys_country', 'str'),
    'sys.sunrise$int': ('sunrise', 'datetime'),
    'sys.sunset$int': ('sunset', 'datetime'),
    'timezone$int': ('timezone', 'int'),
    'id$int': ('id', 'int'),
    'name': ('name', 'str'),
    'cod$int': ('cod', 'int'),
    'wind.gust$float': ('wind_gust', 'float'),
    'rain.1h$float': ('rain_1h', 'float')
}

weather_data_df = rename_and_convert_columns(weather_data_df, weather_column_map)
weather_data_df['local_time'] = weather_data_df.apply(
    lambda row: calculate_local_time(row['date_time'], row['latitude'], row['longitude']),
    axis=1
)

    # Define the columns to keep
required_columns = [
    'city_id',  'date_time', 'local_time','temperature', 'feels_like', 'temp_min', 'temp_max',
    'pressure', 'humidity', 'visibility', 'wind_speed', 'wind_deg', 'clouds_all',
    'weather_main', 'weather_description', 'weather_icon', 'sunrise', 'sunset'
]

    # Filter DataFrame to keep only the required columns
weather_data_df = weather_data_df[required_columns]


# Change the column names, format and dtypes for the pollution data 
flattened_pollution_data = [flatten(item) for item in OW_pollution_data]

pollution_data_df = pd.DataFrame(flattened_pollution_data)

        # Define a mapping for column renaming and data type conversions
pollution_column_map = {
    'city_id$int': ('city_id', 'int'),
    'list.[0].dt$int': ('date_time', 'datetime'),
    'longitude$float': ('longitude', 'float'),
    'latitude$float': ('latitude', 'float'),
    'list.[0].main.aqi$int': ('aqi', 'int'),
    'list.[0].components.co$float': ('co', 'float'),
    'list.[0].components.no$int': ('no', 'floT'),
    'list.[0].components.no2$float': ('no2', 'float'),
    'list.[0].components.o3$float': ('o3', 'float'),
    'list.[0].components.so2$float': ('so2', 'float'),
    'list.[0].components.pm2_5$float': ('pm2_5', 'float'),
    'list.[0].components.pm10$float': ('pm10', 'float'),
    'list.[0].components.nh3$float': ('nh3', 'float')
}

        # Rename columns and convert data types
pollution_data_df = rename_and_convert_columns(pollution_data_df, pollution_column_map)

        # Define the columns to keep
required_pollution_columns = [col for col in pollution_column_map.values() if col[0] in pollution_data_df.columns]

        # Filter DataFrame to keep only the required columns
pollution_data_df = pollution_data_df[[col[0] for col in required_pollution_columns]]
pollution_data_df['local_time'] = pollution_data_df.apply(
    lambda row: calculate_local_time(row['date_time'], row['latitude'], row['longitude']),
    axis=1
)

pollution_data_df=pollution_data_df.drop(columns=['latitude','longitude'])


#Upload data to PostgreSQL database 


timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
weather_csv_path = rf'Data\Failed_to_Upload\Weather\Weather_{timestamp}.csv'
pollution_csv_path = rf'Data\Failed_to_Upload\Pollution\pollution_{timestamp}.csv'


# Connect to the PostgreSQL database
conn = psycopg2.connect(dbname=db_name, user=db_user, password=db_pass, host=db_host, port=db_port)
cursor = conn.cursor()

def bulk_insert_pandas(df, table_name):
    columns = ', '.join(df.columns)
    values = ', '.join([f"%({col})s" for col in df.columns])
    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
    
    # Convert DataFrame to list of dicts
    data = df.to_dict(orient='records')
    
    # Execute the bulk insert
    execute_batch(cursor, sql, data)
    conn.commit()


# Upload data
try:
    bulk_insert_pandas(weather_data_df, 'weather')
except Exception as e:
    print(f"Error uploading weather data: {e}")
    weather_data_df.to_csv(weather_csv_path, index=False)

try:
    bulk_insert_pandas(pollution_data_df, 'pollution')
except Exception as e:
    print(f"Error uploading pollution data: {e}")
    pollution_data_df.to_csv(pollution_csv_path, index=False)

# Close the connection
cursor.close()
conn.close()
    