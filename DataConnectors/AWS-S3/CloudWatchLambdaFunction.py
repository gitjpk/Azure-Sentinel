
import boto3
import json
import csv
import time
import pandas as pd
from datetime import datetime
import os

logs = boto3.client('logs')
s3 = boto3.resource('s3')


# Please set the following parameters:
BUCKET_NAME = os.environ['BUCKET_NAME'] # Please enter bucket name
BUCKET_PREFIX = os.environ['BUCKET_PREFIX'] # Please enter bucket prefix that ends with '/' , if no such, leave empty
START_TIME_UTC = datetime.strptime(os.environ['START_TIME_UTC'], '%m/%d/%Y %H:%M') # Please enter start time for exporting logs in the following format: '%m/%d/%Y %H:%M' for example: '12/31/2022 06:55'  pay attention to time differences, here it should be UTC time
END_TIME_UTC = datetime.strptime(os.environ['END_TIME_UTC'], '%m/%d/%Y %H:%M') # Please enter end time for exporting logs in the following format: '%m/%d/%Y %H:%M' for example: '12/31/2022 07:10' pay attention to time differences, here it should be UTC time

def lambda_handler(event, context):
    """
    The function gets data from cloud watch and put it in the desired bucket in the required format for Sentinel.
    :param event: object that contains information about the current state of the execution environment.
    :param context: object that contains information about the current execution context.
    """
    unix_start_time = int(time.mktime(START_TIME_UTC.timetuple()))*1000
    unix_end_time = int(time.mktime(END_TIME_UTC.timetuple()))*1000
    try:
        # List log groups
        try:
            log_groups = logs.describe_log_groups()                   
            log_groups_streams_arry = []
        except Exception as e:            
            print(f"An error occurred at logs.describe_log_groups: {e}")

        for log_group in log_groups['logGroups']:
            log_Group_Name = log_group['logGroupName']            
            try:
                # List log streams for each log group
                log_streams = logs.describe_log_streams(logGroupName=log_Group_Name)                
            except Exception as e:                
                print(f"An error occurred at logs.describe_log_streams: {e}")

            for log_stream in log_streams['logStreams']:
                log_Stream_Name = log_stream['logStreamName']
                logGroup_logStream_entry = {
                    "logGroupName": log_Group_Name,
                    "logStreamName": log_Stream_Name
                }
                log_groups_streams_arry.append(logGroup_logStream_entry) 
        
        # Iterate through log_groups_dict
        for key in log_groups_streams_arry:            
            # Gets objects from cloud watch
            try:
                response = logs.get_log_events(
                    logGroupName = key["logGroupName"],
                    logStreamName = key["logStreamName"],
                    startTime=unix_start_time,
                    endTime=unix_end_time,
                )
            except Exception as e:                
                print(f"An error occurred at get_log_events: {e}")
            
            fileName = key["logStreamName"]
            # Find the index of the closing square bracket
            closing_bracket_index = fileName.find(']')
            # Extract the substring after the closing square bracket
            output_File_Name = fileName[closing_bracket_index + 1]

            # Convert events to json object
            json_string = json.dumps(response)
            json_object = json.loads(json_string)
            
            df = pd.DataFrame(json_object['events'])
            if df.empty:
                print('No events for specified time')                
            
            # Convert unix time to zulu time for example from 1671086934783 to 2022-12-15T06:48:54.783Z
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f').str[:-3]+'Z'
            
            try:
                # Remove unnecessary column
                fileToS3 = df.drop(columns=["ingestionTime"])

                # Export data to temporary file in the right format, which will be deleted as soon as the session ends
                fileToS3.to_csv( f'/tmp/{output_File_Name}.gz', index=False, header=False, compression='gzip', sep = ' ', escapechar=' ',  doublequote=False, quoting=csv.QUOTE_NONE)
            
                # Upload data to desired folder in bucket
                s3.Bucket(BUCKET_NAME).upload_file(f'/tmp/{output_File_Name}.gz', f'{BUCKET_PREFIX}{output_File_Name}.gz')
            except Exception as e:                
                print(f"An error occurred at Upload data to desired folder in bucket: {e}") 
    except Exception as e:
        print("Error exporting %s: %s" % (log_Group_Name, getattr(e, 'message', repr(e))))


