#!/bin/python

import meshtastic
import meshtastic.tcp_interface
import json
import requests
import configparser
import os
import re
from pubsub import pub
import schedule
import time
from datetime import datetime
import datetime
import pytz

#TODO: build a way to support multiple connection types (usb, serial, ble, ip, etc)
#TODO: function to shorten and split text to be sent, and simple loop after it's called to actually do the sending.
#TODO: real logs.
node_ip="192.168.0.44" #should probably be a command line option, and be extended to allow an IP,BLE, or Serial connection.
#conect to node
node=meshtastic.tcp_interface.TCPInterface(node_ip)
config = configparser.ConfigParser()





if os.path.exists('config.ini'):
	config.read('config.ini')
	weather_channel_index = int(config[node_ip]['weather_channel_index'])
	forecast_URL  = config[node_ip]['forecast_URL']
	alert_URL  = config[node_ip]['alert_url']
else:	
	#this whole section should probably be a function that we can call if config.ini isn't found, or if ip isn't found in config.ini
	# Get long, lat, and index of weather channel from node.
#TODO: add error handling here for if no lat/long is set.
	nodeinfo = node.getMyNodeInfo()
	lattitude = nodeinfo["position"]["latitude"]
	longitude = nodeinfo["position"]["longitude"]

	# check to see if weather channel exists
	nodeobject = node.getNode(nodeinfo["num"])
	weather_channel = nodeobject.getChannelByName("weather")
	if weather_channel is None :
		#if the weather channel doesn't exist we'll create it on the next open channel slot
#TODO: Error handling if there isn't another open channel slot.
		NextChannel = nodeobject.getDisabledChannel()
		NextChannel.settings.name = "weather"
		NextChannel.role = "SECONDARY"
		nodeobject.writeChannel(channelIndex = NextChannel.index)
	else:
		weather_channel_index = weather_channel.index
	
	# Use Long and Lat to get forecast and alert urls from weather.gov
	location_data= requests.get("https://api.weather.gov/points/"+str(lattitude)+","+str(longitude))
	forecast_URL = location_data.json()["properties"]["forecast"]
	Alert_zone = location_data.json()["properties"]["forecastZone"] 
	Alert_zone  = re.search("(?:.+\/)(.+)$",Alert_zone).group(1)
	alert_URL = 'https://api.weather.gov/alerts/active/zone/'+Alert_zone
	#write it out to a config file so we don't need to do any of this again. because it's kinda time consuming (particularly finding the weather channel index
	config[node_ip] = {'forecast_URL': forecast_URL,
			'alert_url': alert_URL,
			'weather_channel_index': weather_channel_index}
	with open('config.ini', 'w') as configfile:
		config.write(configfile)
		
		
if os.path.exists('node_positions.ini'):
	config.read('node_positions.ini')		

		

def getlocationforcasturl(lattitude,longitude):
	location_data= requests.get("https://api.weather.gov/points/"+str(lattitude)+","+str(longitude))
	forecast_URL = location_data.json()["properties"]["forecast"]
	return forecast_URL
	
	
	
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
	if 'decoded' in packet:
		if packet['to'] == 3234008964 and  packet['decoded'].get('portnum') == "TEXT_MESSAGE_APP":
			print("DM From"+str(node.nodesByNum.get(packet['from'])))
			print(packet['decoded']['text'])
			print("send reply link to weather channel")
			node.sendText(text="add weather channel to get weather forecast https://meshtastic.org/e/#Cg0aB3dlYXRoZXI6AgggEg8IATgBQAVIAVAeaAHIBgE", destinationId= packet['from'], wantAck = True)
			time.sleep(10)
#TODO: only send this second message if we have a position for that node in the INI file
			node.sendText(text="say \"Forecast\" on that channel for forecast or \"My Forecast\" for forecast from location of your node", destinationId= packet['from'], wantAck = True)
		if 'channel' in packet:
			if packet['channel'] == weather_channel_index  and  packet['decoded'].get('portnum') == "TEXT_MESSAGE_APP":
#TODO: figure out a way that we can work with other nodes on the weather channel also running this script and not both send out forecasts when requested.
				print("looking for requests for forcast here.")
				print(packet['decoded']['text'])
				if packet['decoded']['text'] == "Forecast":
					print("sending forecast two periods")
					SendForecast()
				if packet['decoded']['text'] == "Forecast 3 day":
					print("sending forecast six periods")
					SendForecast(6)
				if packet['decoded']['text'] == "My Forecast":
					print("Localized forecast request from:")
					print(packet['from'])
					#if config[packet['from']]:
					#print(config[packet['from']]['latitude'])
					#print(config[packet['from']]['longitude'])
					#latitude = config[packet['from']]['latitude']
					#longitude = config[packet['from']]['longitude']
					if node.nodesByNum.get(packet['from'])["position"]:
#TODDO: stop looking to the node for locaiton info, check the INI file we've made, can handle more than 100 nodes.
						print(node.nodesByNum.get(packet['from'])["position"]["latitude"])
						print(node.nodesByNum.get(packet['from'])["position"]["longitude"])
						SendForecast(url=getlocationforcasturl(node.nodesByNum.get(packet['from'])["position"]["latitude"], node.nodesByNum.get(packet['from'])["position"]["longitude"]))
					else:
						print("no location in node DB can't send location specific forecast")
						node.sendText(text="Sorry no location in node DB can't sent location specific forecast", channelIndex= weather_channel_index)
		if  packet['decoded'].get('portnum') == "POSITION_APP":

			position = packet['decoded']['position']
			config[packet['from']] = {'latitude': position.get('latitude', 'N/A'),
				'longitude': position.get('longitude', 'N/A')}
			#print(str(packet['from']) +'  latitude:' +  str(position.get('latitude', 'N/A'))+ '  longitude:'+ str(position.get('longitude', 'N/A')))
			with open('node_positions.ini', 'w') as configfile:
				config.write(configfile)

#TODO: replace sleep with a wait for ack.
def SendForecast(Number_of_periods_to_send = 2, url = forecast_URL):
	#open forecast url and collect next forecasts details.
	forecast_data= requests.get(url)
	forecast_periods = forecast_data.json()["properties"]["periods"]
	Max_message_len = 190
	for period in forecast_periods:
		if period["number"] <= Number_of_periods_to_send: #only send next two periods by default, don't want to flood the mesh.
			forecast = period["name"]+"\n"+ period["detailedForecast"]
			#print("Straight forcast  "+forecast)
			if len(forecast) > Max_message_len:  #only shorten things if we need to
				forecast = shorten_forecast(forecast)
			if len(forecast) > Max_message_len: #If it's still to long, we send multiple messages
				match = re.search("(?:.*\. )(.*)$",forecast[:Max_message_len]) #find a period to break it up on instead of the middle of a word
				messsage = node.sendText(text=forecast[:match.start(1)], channelIndex= weather_channel_index, wantAck = True)
				print(forecast[:match.start(1)])
				print(messsage)
				forecast = forecast[match.start(1):]
				time.sleep(10) #pause to make sure messages get sent in order
			messsage = node.sendText(text=forecast, channelIndex= weather_channel_index, wantAck = True)
			print(forecast)
			print(messsage)
		#node.waitForAckNak()
		time.sleep(10) #pause before we loop again to make sure messages get sent in order
		
def CheckAlerts():
	Max_message_len = 190
	print("check for alerts here")
	alert_response= requests.get(alert_URL)
	fiveminutesago = datetime.datetime.now() - datetime.timedelta(minutes=5)
	print(fiveminutesago)
	if len(alert_response.json()["features"] ) >= 1:
		for alert in alert_response.json()["features"]:
			alert_url = alert["id"]
			alert_url  = "https://alerts.weather.gov/id/"+re.search("(?:.+\/)(.+)$",alert_url).group(1)
			alert_headline = alert["properties"]["headline"]
			alert_sent = alert["properties"]["sent"]
			sent_datetime = datetime.datetime.strptime(alert_sent, '%Y-%m-%dT%H:%M:%S%z').replace(tzinfo=None)
			print(sent_datetime)
			msgtext = alert_headline+ " "+alert_url
			if sent_datetime > fiveminutesago:
				if len(msgtext) > Max_message_len:
					match = re.search("(?:.* )(.*)$",msgtext[:Max_message_len]) #find a space to break it up on instead of the middle of a word
					messsage = node.sendText(text=msgtext[:match.start(1)], channelIndex= weather_channel_index, wantAck = True)
					print(msgtext[:match.start(1)] + "|")
					msgtext = msgtext[match.start(1):]
					print(messsage)
					time.sleep(10) 
				messsage = node.sendText(text=msgtext, channelIndex= weather_channel_index, wantAck = True)
				print(msgtext)
				print(messsage)
				time.sleep(10) 
	

pub.subscribe(onReceive, 'meshtastic.receive')
schedule.every().day.at("07:00").do(SendForecast)
schedule.every(5).minutes.do(CheckAlerts)
CheckAlerts()
# TODO: regular heartbeats to make sure TCP connection is still alive. node.sendHeartbeat()
# TODO: check if location is static on node, and if not have a scheduled check of location data.
# TODO: Consider a long fast message once a month? (first wednesday at 1pm during the sirens in MN? announcing that this exists?)
while True:
	schedule.run_pending()
	time.sleep(1)
node.close()