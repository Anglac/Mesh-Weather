#!/bin/python

import meshtastic
import meshtastic.tcp_interface
import json
import requests
import configparser
import os
import re
from pubsub import pub
import time

#TODO: create second script that runs more often to look at for an notify on severe weather alerts at alert_url.


node_ip="192.168.0.44" #should probably be a command line option, and be extended to allow an IP,BLE, or Serial connection.
#conect to node
node=meshtastic.tcp_interface.TCPInterface(node_ip)
config = configparser.ConfigParser()





if os.path.exists('config.ini'):
	config.read('config.ini')
	weather_channel_index = int(config[node_ip]['weather_channel_index'])
	forecast_URL  = config[node_ip]['forecast_URL']
else:	
	#this whole section should probably be a function that we can call if config.ini isn't found, or if ip isn't found in config.ini
	
	# Get long, lat, and index of weather channel from node. -- add error handling here for if no lat/long is set.
	nodeinfo = node.getMyNodeInfo()
	lattitude = nodeinfo["position"]["latitude"]
	longitude = nodeinfo["position"]["longitude"]

	# automatically find weather channel index - add error handling here to either error, or add weather channel.
	nodeobject = node.getNode(nodeinfo["num"])
	weather_channel = nodeobject.getChannelByName("weather")
	weather_channel_index = weather_channel.index
	
	# Use Long and Lat to get forecast and alert urls from weather.gov
	location_data= requests.get("https://api.weather.gov/points/"+str(lattitude)+","+str(longitude))
	forecast_URL = location_data.json()["properties"]["forecast"]
	Alert_zone = location_data.json()["properties"]["forecastZone"] 
	Alert_zone  = re.search("(?:.+\/)(.+)$",Alert_zone).group(1)
	#write it out to a config file so we don't need to do any of this again.
	config[node_ip] = {'forecast_URL': forecast_URL,
			'alert_url':'https://api.weather.gov/alerts/active/zone/'+Alert_zone,
			'weather_channel_index': weather_channel_index}
	with open('config.ini', 'w') as configfile:
		config.write(configfile)
		
		


def shorten_forecast(forecast):
	forecast = re.sub(' temperatures ', ' temps ', forecast)
	forecast = re.sub(' temperature ', ' temp ', forecast)
	forecast = re.sub(' precipitation ', ' precip ', forecast)
	forecast = re.sub(' accumulation ', ' accum ', forecast)
	forecast = re.sub(' North ', ' N ', forecast)
	forecast = re.sub(' West ', ' W ', forecast)
	forecast = re.sub(' East ', ' E ', forecast)
	forecast = re.sub(' South ', ' S ', forecast)
	forecast = re.sub(' [N,n]orthwest ', ' NW ', forecast)
	forecast = re.sub(' [S,s]outhwest ', ' SW ', forecast)
	forecast = re.sub(' [N,n]ortheast ', ' NE ', forecast)
	forecast = re.sub(' [S,s]outheast ', ' SE ', forecast)
	return forecast


def onReceive(packet, interface):
	#print(f"  To: {packet['to']}")
	if 'decoded' in packet:
		#print("decoded")
		#print(packet['decoded'].get('portnum'))
		if packet['to'] == 3234008964 and  packet['decoded'].get('portnum') == "TEXT_MESSAGE_APP":
			print(packet['from']+"add weather channel to get weather forecast https://meshtastic.org/e/#Cg0aB3dlYXRoZXI6AgggEg8IATgBQAVIAVAeaAHIBgE")
			node.sendText(text="add weather channel to get weather forecast https://meshtastic.org/e/#Cg0aB3dlYXRoZXI6AgggEg8IATgBQAVIAVAeaAHIBgE", destinationId= packet['from'])
		if 'channel' in packet:
			#print(f"  Channel: {packet['channel']}")
			if packet['channel'] == weather_channel_index  and  packet['decoded'].get('portnum') == "TEXT_MESSAGE_APP":
				print("looking for requests for forcast here.")
				print(packet['decoded']['text'])
				if packet['decoded']['text'] == "Forecast":
					print("sending forecast two periods")
					SendForecast()
				if packet['decoded']['text'] == "Forecast 3 day":
					print("sending forecast six periods")
					SendForecast(6)




def SendForecast(Number_of_periods_to_send = 2):
	#open forecast url and collect next forecasts details.
	forecast_data= requests.get(forecast_URL)
	forecast_periods = forecast_data.json()["properties"]["periods"]

	Max_message_len = 220

	#might need add some pauses to ensure message get sent in order.
	for period in forecast_periods:
		if period["number"] <= Number_of_periods_to_send: #only send next two periods, don't want to flood the mesh.
			forecast = period["name"]+"\n"+ period["detailedForecast"]
			#print("Straight forcast  "+forecast)
			if len(forecast) > Max_message_len:  #only shorten things if we need to
				forecast = shorten_forecast(forecast)
			if len(forecast) > Max_message_len: #If it's still to long, we send multiple messages
				match = re.search("(?:.*\. )(.*)$",forecast[:Max_message_len]) #find a period to break it up on instead of the middle of a word
				node.sendText(text=forecast[:match.start(1)], channelIndex= weather_channel_index)
				print(forecast[:match.start(1)])
				forecast = forecast[match.start(1):]
			node.sendText(text=forecast, channelIndex= weather_channel_index)
			print(forecast)
		time.sleep(15)

pub.subscribe(onReceive, 'meshtastic.receive')

# TODO: regular heartbeats to make sure TCP connection is still alive, schedule forecast to send at particular times. node.sendHeartbeat()
while True:
    time.sleep(1)
node.close()