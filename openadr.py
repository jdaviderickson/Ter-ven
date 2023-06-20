"""Controller for OpenADR VTN and VEN"""

import os
import requests
from requests.auth import HTTPBasicAuth
import json
import pytz

from datetime import datetime, date, timedelta
import time
import logging
from openleadr import enums
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import sys, getopt

# fuss around to import in various scenarios, e.g. code/ter.py, code/openadr/openadr.py
try:
    from openadr.vtn import VTN
except ImportError:
    try:
        from vtn import VTN
    except ImportError:
        try:
            from .vtn import VTN
        except ImportError:
            pass
        else:
            pass
    else:
        pass
else:
    pass

TER_HOST = os.getenv('TER_HOST', '127.0.0.1')
PRICES_URL = TER_HOST + '/prices/today/'
PRICES_USER = os.getenv('PRICES_USER', 'admin')
PRICES_PSWD= os.getenv('PRICES_PSWD', 'adPswd12*')

SIGNAL_DURATION = timedelta(minutes=60)
EVENT_POLL_PERIOD = int(os.getenv('EVENT_POLL_PERIOD', '1200'))
REPORTING_INTERVAL = timedelta(seconds=int(os.getenv('REPORTING_INTERVAL', '12')))  # demo/debug
SAMPLING_INTERVAL = timedelta(seconds=int(os.getenv('SAMPLING_INTERVAL', '2')))
VTN_REMOTE_HOST = os.getenv('VTN_HOST')
VTN_LOCALHOST = "127.0.0.1"

logging.basicConfig()
logger = logging.getLogger('openadr')
logger.setLevel(level=logging.DEBUG)

class OPENADR():
    """Controller for OpenADR VTN and VEN"""
        # last_event_date keeps track of sent event to help prevent duplicates. Initialized to a time in the past
    last_event_date = str(datetime(2000, 1, 1, 0, 0, 0, 0, pytz.UTC))
    
    def __init__(self, reporting_interval, sampling_interval, host):
        logger.info("OPENADR.init()")
        self._vtn=VTN(reporting_interval, sampling_interval, host)

    def start(self):
        """Start VTN and event poller"""
        logger.debug(f"OPENADR.start() start VTN in thread")
        self._vtn.start_thread()

        logger.debug(f"OPENADR.start() start event_poll in scheduler")
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.event_poll, 'interval', seconds=EVENT_POLL_PERIOD)
        scheduler.start()

        logger.debug(f"OPENADR.start() loop in main thread")
        try:
            # This is here to simulate application activity (which keeps the main thread alive).
            while True:
                time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            # Not strictly necessary if daemonic mode is enabled but should be done if possible
            scheduler.shutdown()

    def event_poll(self):
        """Loop sends daily price schedules as events to VEN"""
        logger.info(f"OPENADR.event_poll()")

        # Periodically fetch prices and instruct VTN to send to VEN
        # bounce until we have at least one VEN registered
        if not self._vtn.get_ven_ids():
            logger.debug(f"OPENADR.event_poll() no VENS")
            return

        s = self.get_latest_prices()
        if s is not None:
            # check if event with this date has already been sent
            if s["date"] == self.last_event_date:
                logging.debug(f"OPENADR.event_poll(): event for this date={self.last_event_date} already sent")
                return

            self.last_event_date = s["date"]
            prices = s["prices"]
            logger.debug(f"OPENADR.event_poll()  prices={prices}")
            intervals = []
            for p in prices:
                try:
                    # datetime field must contain strings in the following format: 2022-01-28T0:0:0+0000"
                    dstart = datetime.strptime(p["datetime"], '%Y-%m-%dT%H:%M:%S%z')
                    interval = {'dtstart': dstart,
                              'duration': SIGNAL_DURATION,
                              'signal_payload': float(p["price"])}
                    intervals.append(interval)
                except:
                    dt = p["datetime"]
                    logger.warning(f"OPENADR.event_poll() price schedule datetime appears to be in wrong format {dt}")

            # send event to every VEN
            for v in self._vtn.get_ven_ids():
                self.add_event(v, intervals)
        else:
            logger.debug(f"OPENADR.event_poll(), No price Schedule found")

    def get_latest_prices(self):
        # response = requests.get(PRICES_URL)
        
        response = requests.get(PRICES_URL, auth=HTTPBasicAuth(PRICES_USER, PRICES_PSWD))
        if response.status_code != 200:
            logger.warning(f"OPENADR.get_latest_prices() response.status_code={response.status_code}")
            return None
           
        latest = response.json()
        logger.debug(f"OPENADR.get_latest_prices() prices={latest}")
        return latest
    

    def add_event(self, ven_id, intervals):
        """Send a pricing signal to VEN"""
        logger.info(f"OPENADR.add_event(): ven_id={ven_id}")
        logger.debug(f"OPENADR.add_event(ven_id={ven_id}, intervals={intervals})")
        try:
            self._vtn.add_event(
                ven_id=ven_id,
                signal_name=enums.SIGNAL_NAME.ELECTRICITY_PRICE,
                signal_type=enums.SIGNAL_TYPE.PRICE,
                intervals=intervals)
        except Exception as e:
            logger.warning(f"OPENADR.add_event(), exception={e}")


def main(argv):
    logger.info(f"OPENADR.main()")

    reporting_interval = REPORTING_INTERVAL
    sampling_interval = SAMPLING_INTERVAL
    host = VTN_REMOTE_HOST
    try:
        opts, args = getopt.getopt(argv, "hr:s:l", ["reporting_interval=", "sampling_interval="])
    except getopt.GetoptError:
        print(f"usage: -h usage -r <reporting_interval> -s <sampling_interval> -l localhost. Defaults: reporting_interval={reporting_interval} sampling_interval={sampling_interval} host={host}")
        sys.exit(2)
    for opt, arg in opts:
        logger.info(f"opt={opt} arg={arg} ")
        if opt == '-h':
            print(
                f"usage: -h usage -r <reporting_interval> -s <sampling_interval>. Defaults: reporting_interval={reporting_interval} sampling_interval={sampling_interval} host={host}")
            sys.exit()
        elif opt in ("-r", "--reporting_interval"):
            reporting_interval = timedelta(seconds=int(arg))
        elif opt in ("-s", "--sampling_interval"):
            sampling_interval = timedelta(seconds=int(arg))
        elif opt in ("-l"):
            # when running on same host as VEN must use 127.0.0.1, otherwise 0.0.0.0
            host = VTN_LOCALHOST
    logger.info(f"VEN.main() reporting_interval={reporting_interval} sampling_interval={sampling_interval} host={host}")

    adr = OPENADR(reporting_interval, sampling_interval, host)
    adr.start()

if __name__ == "__main__":
    main(sys.argv[1:])
