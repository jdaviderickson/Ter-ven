"""VEN wrapper to openleadr client"""

import asyncio
import threading
from datetime import timedelta, datetime
from openleadr import OpenADRClient
import logging
import sys, getopt

import openleadr
openleadr.enable_default_logging(level=logging.DEBUG)

import csv

logging.basicConfig()
logger = logging.getLogger('ven')
logger.setLevel(level=logging.DEBUG)

VEN_NAME = "Generac_VEN"
VEN_ID = "ENBALA_VEN_NHEC1"
#VEN_ID = "ENBALA_VEN_QA"
#VEN_ID = "NHEC_test_01"
#VTN_HOST = '20.231.98.1'
#VTN_HOST = 'vtn.nhecter.com/oEmWxBmfkhhKC0FUVStCdA8GP8eIEx4qoPOlqRofoC0'
#VTN_HOST = 'vtn.nhecter.com/r1WjgWUfODO42x4Xip49vsh8iqP5Q166OV5Nvu0LP6M'
#VTN_HOST = 'vtn.nhecter.com/NvswL0jECtYp85fczsoo2TzamvgvzWyh45KOGemIssw'
VTN_HOST = 'vtn.nhecter.com/sgiaQ69mEG-FcudKRAZWpxImjEv6t0AAPdzedqTWwAE'
#VTN_HOST = 'vtn.nhecter.com/ox4r-KQgPqlWKbW119RG0vgaWThAqP32CBW3NO2Qpqk'
SAMPLING_RATE = timedelta(hours=1)
REPORT_DURATION = timedelta(hours=24)
STATUS_SAMPLING_RATE = timedelta(seconds=30)
#RESOURCE_ID = '06162'
#RESOURCE_ID = 'Battery-XVT07-13726'
#RESOURCE_ID = 'NHEC_test_device_01'
#RESOURCE_ID = 'enbala-test-device-001'
#RESOURCE_ID = 'DEVICEABS123DCN5555555'
RESOURCE_ID = 'devlinX1'
#RESOURCE_ID = 'X2'
ENERGY_REAL = 'RealEnergy'
TELEMETRY_STATUS = 'TELEMETRY_STATUS'
REAL_ENERGY = 'RealEnergy'

class VEN():
    """VEN wrapper to openleadr client"""

    def __init__(self, ven_id, resource_id, vtn_host, sampling_rate):
        """VEN init"""
        logger.info("VEN.__init__()")

        #vtn_url = f'http://{vtn_host}:8082/OpenADR2/Simple/2.0b'
        vtn_url = f'https://{vtn_host}/OpenADR2/Simple/2.0b'
        logger.debug(f"VEN init() vtn_url={vtn_url}")

        # Create the client object
        try:
            self.client = OpenADRClient(ven_name=VEN_NAME,
                                        ven_id=ven_id,
                                        vtn_url=vtn_url)
        except Exception as e:
            logger.warning(f"VEN.__init__(), exception={e}")
            sys.exit()

        self.client.add_report(callback=self.collect_status,
                                resource_id=resource_id,
                                report_name=TELEMETRY_STATUS,
                                sampling_rate=STATUS_SAMPLING_RATE)

        self.client.add_report(callback=self.collect_usage,
                                resource_id=resource_id,
                                measurement=REAL_ENERGY,
                                scale="k",
                                unit="Wh",
                                sampling_rate=SAMPLING_RATE,
                                report_duration=REPORT_DURATION)

        # Add event handling capability to the client
        self.client.add_handler('on_event', self.handle_event)

    async def collect_usage(self):
        """This callback is called when you need to collect a value for your Report"""
        logger.info(f"VEN.collect_report_value() \n")
        intervals = []
        with open('g:\\ven test\\battery_telemetry.csv', newline='') as csvfile:
          reader = csv.DictReader(csvfile)
          for row in reader: 
        #for i in range(24):
            # for debugging, map 1 sec sampling_intervals to hours
            # interval = [dt + ((sampling_interval*360) * i), 0.01 * i]
            #dt = datetime.now()
            #dt = dt.replace(hour=i, minute=0, second=0, microsecond=0)

            #value = 0.01 * i
            #if i > 12 and i < 18:
            #    value = 0 - value
            #interval = [dt, value]
                interval = [row['interval_end'], row['value']]

                intervals.append(interval)
        return intervals

    async def collect_status(self):
        logger.info(f"VEN.collect_status() \n")

        interval = {'dtstart': datetime.now(), 'resource_status': {'online': True, 'manual_override': False, 'capacity': {'min': 0, 'max': 10, 'current': 5, 'normal': 8}}}
        capacity = {'capacity': {'min': 0,
                      'max': 10,
                      'current': 5,
                      'normal': 8}}
        return (datetime.now(), True, False, capacity)

    async def handle_event(self, event):
        """This callback receives an Event dict."""
        logger.info(f"VEN.handle_event() event={event}\n" )
        for s in event["event_signals"]:
            for p in s["intervals"]:
                logger.debug(f"VEN.handle_event signal_payload :{p}" )
        return 'optIn'

    def start_async(self):
        """Run the client in the Python AsyncIO Event Loop"""
        logger.info("VEN.start_async()")
        # despite python.org recommendation, this produces errors from openleadr client aiohttp
        # asyncio.run(self.client.run(), debug=True)

        try:
            loop = asyncio.get_event_loop()
            loop.set_debug(1)
            loop.create_task(self.client.run())
            loop.run_forever()
        except Exception as e:
            logger.error(f"VEN.start_async() async loop error = {e}")
            pass
        finally:
            loop.close()

    def start_thread(self):
        """Run the client in a separate thread"""
        logger.info("VEN.start_thread()")
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever).start()
        future = asyncio.run_coroutine_threadsafe(self.client.run(), self._loop)

    def stop(self):
        logger.info("VEN.stop()")
        self.client.stop()

def main(argv):
    """VEN main"""
    logger.info("VEN.main()")
    ven_id = VEN_ID
    resource_id = RESOURCE_ID
    vtn_host = VTN_HOST
    sampling_rate = SAMPLING_RATE
    # logger.debug(f"Argument List: {str(argv)}")
    try:
        opts, args = getopt.getopt(argv, "hi:d:v:s:", ["VEN_id=", "device_id=", "VTN_host=", "sampling_rate="])
    except getopt.GetoptError:
        print(f"usage: -h usage -n <VEN_name> -d <device_id> -v <VTN_host> -s <sampling_rate>. /"
                       f"Defaults: ven_id={ven_id} device_id={resource_id} vtn_host={vtn_host} sampling_rate={sampling_rate}")
        sys.exit(2)
    for opt, arg in opts:
        logger.debug(f"opt={opt} arg={arg} ")
        if opt == '-h':
            print(f"usage: -h usage -n <VEN_name> -d <device_id> -v <VTN_host> -s <sampling_rate>. /"
                           f"Defaults: ven_id={ven_id} device_id={resource_id} vtn_host={vtn_host} sampling_rate={sampling_rate}")
            sys.exit()
        elif opt in ("-i", "--VEN_id"):
            ven_id = arg
        elif opt in ("-d", "--device_id"):
            resource_id = arg
        elif opt in ("-v", "--VTN_host"):
            vtn_host = arg
        elif opt in ("-s", "--sampling_rate"):
            sampling_rate = timedelta(seconds=int(arg))

    logger.info(f"VEN.main() ven_id={ven_id} resource_id={resource_id} vtn_host={vtn_host} sampling_rate={sampling_rate}")

    ven = VEN(ven_id, resource_id, vtn_host, sampling_rate)
    ven.start_async()
    # will never reach this statement as thread will be consumed by asyncio loop
    logger.info("VEN: started async loop")

if __name__ == "__main__":
    main(sys.argv[1:])
