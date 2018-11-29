from threading import Thread
import time
import serial
import datetime

import os
import random
import ssl

import jwt
import paho.mqtt.client as mqtt

# Settings for the user to change
serialPort = 'COM3'
frequencyLogfile = 60 # Number of entry records per minute (at equal intervals)
frequencyMQTT = 5 # Number of MQTT telemetry reports per minute (at equal intervals)
filePath = "C:\\Users\\Tiago Cabral\\Desktop\\logfile.csv" # Full file path, properly escaped 
# Make sure the script has permissions to write in the folder!


### Excel does not meet the csv standards. To correctly import in Excel either:
## Add SEP=, in the first line (not required for other softwares, will appear as a value in other softwares)
## Change the extension to .txt and run the Text Importing Assistant

# End of Settings

frc = 1/(frequencyLogfile / 60)
frcMQTT = 1/(frequencyMQTT / 60)
buffer = True if (frc != frcMQTT) else False
vals = [] * 8
dhMean = 0
dhMeanList = [0.0 , 0.0]
dhMeanListWrites = 0
dhMeanLastWrite = -1
dhTargetDev = 1.8
dhTargetMeanJump = 0.25
bufferList = []
valPTAT = 0
connected = False
debug = False

class GCloudIOT():
        # The initial backoff time after a disconnection occurs, in seconds.
        minimum_backoff_time = 1

        # The maximum backoff time before giving up, in seconds.
        MAXIMUM_BACKOFF_TIME = 32

        # Whether to wait with exponential backoff before publishing.
        should_backoff = False

        # Configuration
        arg_project_id = 'iot-test-0001' #GCP Cloud Project ID
        arg_registry_id = 'test-iot' #Cloud IoT Core registry NAME
        arg_device_id = 'device-python' #Cloud IoT Core device NAME
        arg_private_key_file = 'C:\\Users\\Tiago Cabral\\Desktop\\mqtt_python_test\\rsa_private.pem' #Path to private key file
        arg_algorithm = 'RS256' #Encryption to generate JWT, RS256 or ES256 available
        arg_cloud_region = 'europe-west1' #GCP Cloud Region
        arg_ca_certs = 'C:\\Users\\Tiago Cabral\\Desktop\\mqtt_python_test\\roots.pem' #Path to CA root obtained from https://pki.google.com/roots.pem
        arg_message_type = 'event' #Event (telemetry) or State(device state)
        arg_mqtt_bridge_hostname = 'mqtt.googleapis.com' #MQTT bridge hostname
        arg_mqtt_bridge_port = 8883 #MQTT bridge port, 8883 or 443 recommended
        arg_jwt_expires_minutes = 20 #Expiration time, in minutes, for JWT tokens



        # [START iot_mqtt_jwt]
        def create_jwt(self, project_id, private_key_file, algorithm):

                token = {
                        # The time that the token was issued at
                        'iat': datetime.datetime.utcnow(),
                        # The time the token expires.
                        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
                        # The audience field should always be set to the GCP project id.
                        'aud': project_id
                }

                # Read the private key file.
                with open(private_key_file, 'r') as f:
                        private_key = f.read()

                print('Creating JWT using {} from private key file {}'.format(
                algorithm, private_key_file))

                return jwt.encode(token, private_key, algorithm=algorithm)
        # [END iot_mqtt_jwt]


        # [START iot_mqtt_config]
        def error_str(self, rc):
                """Convert a Paho error to a human readable string."""
                return '{}: {}'.format(rc, mqtt.error_string(rc))


        def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
                """Callback for when a device connects."""
                print('on_connect', mqtt.connack_string(rc))

        # After a successful connect, reset backoff time and stop backing off.
                should_backoff = self.should_backoff
                minimum_backoff_time = self.minimum_backoff_time
                should_backoff = False
                minimum_backoff_time = 1


        def on_disconnect(self, unused_client, unused_userdata, rc):
                """Paho callback for when a device disconnects."""
                print('on_disconnect', self.error_str(rc))

                # Since a disconnect occurred, the next loop iteration will wait with
                # exponential backoff.
                should_backoff = self.should_backoff
                should_backoff = True


        def on_publish(self, unused_client, unused_userdata, unused_mid):
                """Paho callback when a message is sent to the broker."""
                print('on_publish')


        def on_message(self, unused_client, unused_userdata, message):
                """Callback when the device receives a message on a subscription."""
                payload = str(message.payload)
                print('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
                payload, message.topic, str(message.qos)))


        def get_client(self,
                project_id, cloud_region, registry_id, device_id, private_key_file,
                algorithm, ca_certs, mqtt_bridge_hostname, mqtt_bridge_port):
                """Create our MQTT client. The client_id is a unique string that identifies
                this device. For Google Cloud IoT Core, it must be in the format below."""
                client = mqtt.Client(
                        client_id=('projects/{}/locations/{}/registries/{}/devices/{}'
                                .format(
                                project_id,
                                cloud_region,
                                registry_id,
                                device_id)))

                # With Google Cloud IoT Core, the username field is ignored, and the
                # password field is used to transmit a JWT to authorize the device.
                client.username_pw_set(
                        username='unused',
                        password=self.create_jwt(
                        project_id, private_key_file, algorithm))

                # Enable SSL/TLS support.
                client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)

                # Register message callbacks. https://eclipse.org/paho/clients/python/docs/
                # describes additional callbacks that Paho supports. In this example, the
                # callbacks just print to standard out.
                client.on_connect = self.on_connect
                client.on_publish = self.on_publish
                client.on_disconnect = self.on_disconnect
                client.on_message = self.on_message

                # Connect to the Google MQTT bridge.
                client.connect(mqtt_bridge_hostname, mqtt_bridge_port)

                # This is the topic that the device will receive configuration updates on.
                mqtt_config_topic = '/devices/{}/config'.format(device_id)

                # Subscribe to the config topic.
                client.subscribe(mqtt_config_topic, qos=1)

                return client
        # [END iot_mqtt_config]


        # [START iot_mqtt_run]
        def main(self):

                minimum_backoff_time = self.minimum_backoff_time
                arg_project_id = self.arg_project_id
                arg_registry_id = self.arg_registry_id
                arg_device_id = self.arg_device_id
                arg_private_key_file = self.arg_private_key_file
                arg_algorithm = self.arg_algorithm
                arg_cloud_region = self.arg_cloud_region
                arg_ca_certs = self.arg_ca_certs
                arg_message_type = self.arg_message_type
                arg_mqtt_bridge_hostname = self.arg_mqtt_bridge_hostname
                arg_mqtt_bridge_port = self.arg_mqtt_bridge_port
                arg_jwt_expires_minutes = self.arg_jwt_expires_minutes

                global frcMQTT

                # Publish to the events or state topic based on the flag.
                sub_topic = 'events' if arg_message_type == 'event' else 'state'

                mqtt_topic = '/devices/{}/{}'.format(arg_device_id, sub_topic)

                jwt_iat = datetime.datetime.utcnow()
                jwt_exp_mins = arg_jwt_expires_minutes
                client = self.get_client(
                        arg_project_id, arg_cloud_region, arg_registry_id, arg_device_id,
                        arg_private_key_file, arg_algorithm, arg_ca_certs,
                        arg_mqtt_bridge_hostname, arg_mqtt_bridge_port)

                # Publish mesages to the MQTT bridge.
                while(True):
                        # Process network events.
                        client.loop()

                        # Wait if backoff is required.
                        if self.should_backoff:
                        # If backoff time is too large, give up.
                                if minimum_backoff_time > self.MAXIMUM_BACKOFF_TIME:
                                        print('Exceeded maximum backoff time. Giving up.')
                                        break

                        # Otherwise, wait and connect again.
                                delay = minimum_backoff_time + random.randint(0, 1000) / 1000.0
                                print('Waiting for {} before reconnecting.'.format(delay))
                                time.sleep(delay)
                                minimum_backoff_time *= 2
                                client.connect(arg_mqtt_bridge_hostname, arg_mqtt_bridge_port)

                        #Processing the buffer into our JSON object format
                        if (len(bufferList)>=(frcMQTT-1)):
                                
                                payload = ''
                                for x in range(len(bufferList)):
                                        row = '{'
                                        for y in range(8):
                                                row = row + '"s'+str(y+1)+'":"'+str(bufferList[x][y])+'",'
                                        row = row + '"time":"' + str(bufferList[x][8]) + '"}'
                                        if (x<len(bufferList)-1):
                                                row = row + ';'
                                        payload = payload + row
                                
                                print('Publishing message: \'{}\''.format(payload))
                                # [START iot_mqtt_jwt_refresh]
                                seconds_since_issue = (datetime.datetime.utcnow() - jwt_iat).seconds
                                if seconds_since_issue > 60 * jwt_exp_mins:
                                        print('Refreshing token after {}s').format(seconds_since_issue)
                                        jwt_iat = datetime.datetime.utcnow()
                                        client = self.get_client(
                                                arg_project_id, arg_cloud_region,
                                                arg_registry_id, arg_device_id, arg_private_key_file,
                                                arg_algorithm, arg_ca_certs, arg_mqtt_bridge_hostname,
                                                arg_mqtt_bridge_port)
                                # [END iot_mqtt_jwt_refresh]
                                # Publish "payload" to the MQTT topic. qos=1 means at least once
                                # delivery. Cloud IoT Core also supports qos=0 for at most once
                                # delivery.
                                client.publish(mqtt_topic, payload, qos=1)
                                bufferList.clear() # This is not supported on older Python versions, only 3.3+
                        else:
                                #This is in case it's out of sync, we wait 1 second so it possibly fixes the issue
                                time.sleep(1)
                                continue
                        
                        # We're publishing the buffer 5 times per minute, to save on queries.
                        time.sleep(frcMQTT)

                print('Finished.')
        # [END iot_mqtt_run]

class DetectHuman():
        def updateTo(self, arg):
                global dhMean
                global dhMeanLastWrite

                dhMean = arg
                dhMeanLastWrite = time.time()

        def updateMeanList(self, arg):
                global dhMeanListWrites
                dhMeanList[0] = dhMeanList[1]
                dhMeanList[1] = arg
                dhMeanListWrites += 1
        
        def calcMean(self, arg): #Takes a list, calculates the mean of the entire list, returns float
                data = []
                for i in arg:
                        data.append(int(i))

                return (sum(data)/float(len(data)))
        
        def calcDev(self, arg): #Takes a list, calculates the deviation for each value, returns a list with the deviation values
                valMean = self.calcMean(arg)
                data = []
                for i in arg:
                        data.append(int(i))
                devList = []
                for i in data:
                        dev = abs(valMean - i)
                        devList.append(dev)
                return devList
                        
class SerialThread(Thread):
 
    def __init__(self):
        Thread.__init__(self)
        
    def run(self):
        while True:
            print("Attempting to connect")
            try:
                global serialPort
                conn = serial.Serial(serialPort, 9600)
                break
            except serial.SerialException as e:
                print("Fail to connect: {}".format(e))
                time.sleep(3)
        time.sleep(2)

        print("Listening")

        global vals

        while True:
            if not vals:
                vals = [0]*8
            else:
                global valPTAT
                ler = conn.readline().decode()
                ler = ler.strip()
                temp = ler.split(",")
                for i in range(8):
                        vals[i] = temp[i]
                
                valPTAT = temp[8]

                global connected
                connected = True
            
                if debug:
                    print("Values: {}".format(vals))
                    print("PTAT Value: {}".format(valPTAT))



class DataThread(Thread):
 
    def __init__(self):
        Thread.__init__(self)
        
    def run(self):
        while(True):
            if vals:
                ts = time.time()
                st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d,%H:%M:%S')
                
                F = open(filePath, 'a')
                stringPrint = st + ','
                
                #Writing the new data to the Buffer
                global buffer
                if buffer:
                        bufferVal = []
                        bufferVal.extend(vals)
                        bufferVal.append(st)
                        bufferList.append(bufferVal)
                
                for x in vals:
                        stringPrint = stringPrint + str(x) + ','
                stringPrint = stringPrint + str(valPTAT) + '\n'

                #Writing the new line in the file
                F.write(stringPrint)
                
                #Waiting for the interval so we don't write too fast
                time.sleep(frc)

class DetectHumanThread(Thread):
        def __init__(self):
                Thread.__init__(self)
        
        def run(self):
                while(True):
                        global connected

                        if connected:
                                global dhTargetDev
                                global dhTargetMeanJump

                                currentMean = DetectHuman().calcMean(vals)
                                print("Current mean is {}".format(currentMean))
                                
                                global dhMeanLastWrite
                                if dhMeanLastWrite == -1: #This means it's the first time getting a value
                                        DetectHuman().updateTo(currentMean)
                                
                                currentDev = DetectHuman().calcDev(vals)
                                if(max(currentDev)>=dhTargetDev):
                                        print("1 Value too different. Human?")
                                
                                if(dhMeanLastWrite-time.time())>=60 and dhMeanLastWrite!=-1:
                                        DetectHuman().updateTo(currentMean)
                                
                                DetectHuman().updateMeanList(currentMean) #updates meanList with currentValue
                                if(dhMeanListWrites>2):
                                        if(dhMeanList[1]-dhMeanList[0])>dhTargetMeanJump:
                                                print("Sudden bump in mean. Human?")
                                
                                time.sleep(frc)

class GCPThread(Thread):
        def __init__(self):
                Thread.__init__(self)
        
        def run(self):
                GCloudIOT().main()



if __name__ == '__main__':
        
        thread1 = SerialThread()
        thread1.setName('Thread 1')
        
        thread2 = DataThread()
        thread2.setName('Thread 2')

        thread3 = GCPThread()
        thread3.setName('Thread 3')

        thread4 = DetectHumanThread()
        thread4.setName('Thread 4')

        thread1.start()
        thread2.start()
        thread3.start()
        thread4.start()
        
        thread1.join()
        thread2.join()
        thread3.join()
        thread4.join()
        
        print('Main Terminating...')

