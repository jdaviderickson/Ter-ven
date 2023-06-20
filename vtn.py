"""VTN wrapper to openleadr server"""
import asyncio
import threading
# from openleadr import OpenADRServer
import openleadr
from openleadr.server import OpenADRServer
from functools import partial
from datetime import timedelta
import logging
import sys, getopt, os

# fuss around to import in various scenarios, e.g. code/ter.py, code/openadr/openadr.py, code/openadr/vtn.py
try:
    from openadr.api import OPENADRAPI
except ImportError:
    try:
        from api import OPENADRAPI
    except ImportError:
        try:
            from .api import OPENADRAPI
        except ImportError:
            pass
        else:
            pass
    else:
        pass
else:
    pass

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('vtn')
logger.setLevel(logging.DEBUG)

openleadr.enable_default_logging(level=logging.DEBUG)

VTN_ID = "ter_vtn_1.0"
VTN_LOCALHOST = "127.0.0.1"
VTN_REMOTE_HOST = "0.0.0.0"
# switch as necessary
VTN_HOST = VTN_REMOTE_HOST
VTN_PORT = 8082
REGISTRATION_ID = 'reg_id_123'
POLL_FREQUENCY = timedelta(seconds=120)
DEFAULT_REPORTING_INTERVAL = timedelta(seconds=int(os.getenv('DEFAULT_REPORTING_INTERVAL', '12')))  # demo/debug
DEFAULT_SAMPLING_INTERVAL = timedelta(seconds=2)
STATUS_REPORTING_INTERVAL = timedelta(seconds=16)
MARKET_CONTEXT = 'https://nhec-prod-droms.autogridsystems.net/uop/utility_programs/1024'

class VTN():
    """VTN wrapper to openleadr server"""
    _ven_ids = []
    _ven_count = 0

    def __init__(self, reporting_interval, sampling_interval, host):
        """VTN init"""
        logger.info("VTN init")
        self.reporting_interval = reporting_interval
        self.sampling_interval = sampling_interval

         # Create the server object
        self.server = OpenADRServer(vtn_id=VTN_ID, http_host=host, http_port=VTN_PORT, requested_poll_freq=POLL_FREQUENCY)

        # Add the handler for client (VEN) registrations
        self.server.add_handler('on_create_party_registration', self.on_create_party_registration)

        # Add the handler for report registrations from the VEN
        self.server.add_handler('on_register_report', self.on_register_report)

        # Add the handler for reports from the VEN - this seems unecessary
        # self.server.add_handler('on_update_report', self.on_update_report)

        # Add the handler for events requested from VEN(?)
        self.server.add_handler('on_request_event', self.on_request_event)

    async def on_create_party_registration(self, registration_info):
        """
        Inspect the registration info and return a ven_id and registration_id.
        """
        logger.info(f"VTN.on_create_party_registration(): registration_info = {registration_info}")

        ven_id = registration_info['ven_id']
        # VEN must be pre-registered
        if OPENADRAPI.get_meter(ven_id=ven_id) is None:
            logger.warning(f"VTN.on_create_party_registration(): ven_id {ven_id} not pre-registered!")
            return False

        self._ven_ids.append(ven_id)
        self._ven_count += 1

        registration_id = REGISTRATION_ID
        return ven_id, registration_id

    async def on_register_report(self, ven_id, resource_id, measurement, unit, scale,
                                 min_sampling_interval, max_sampling_interval):
        """
        Inspect a report offering from the VEN and return a callback and sampling interval for receiving the reports.
        """
        logger.info(f"VTN.on_register_report(): ven_id={ven_id} resource_id={resource_id} measurement={measurement} min_sampling_interval={min_sampling_interval} max_sampling_interval={max_sampling_interval}")

        # VEN must be registered
        found = False
        for i in self._ven_ids:
            if i == ven_id:
                found = True
                break

        if not found:
            logger.warning(f"VTN.on_register_report(): ven {ven_id} not found!")
            return None

        # openleadr is tricky, as 'report_name" shows up here in measurement
        # TBD: do we need different sample intervals periods for each report? prob yes
        if measurement == 'Status':
            callback = partial(self.on_status_report, ven_id=ven_id, resource_id=resource_id, measurement=measurement)
            # reporting interval must not be less than sampling rate
            report_interval = max(min_sampling_interval, STATUS_REPORTING_INTERVAL)
            logger.info(f"VTN.on_register_report(): Status - min_sampling_interval={min_sampling_interval} report_interval={report_interval}")
            return callback, min_sampling_interval, report_interval
        elif measurement == 'RealEnergy' or measurement == 'energyReal':
            callback = partial(self.on_energy_usage_report, ven_id=ven_id, resource_id=resource_id, measurement=measurement)
            self.sampling_interval = max(min_sampling_interval, self.sampling_interval)
            self.sampling_interval = min(max_sampling_interval, self.sampling_interval)
            # self.reporting_interval = max(self.sampling_interval, self.reporting_interval)
            # ensure sampling and reporting rate are the same, as our use case just samples and reports
            self.reporting_interval = DEFAULT_REPORTING_INTERVAL

            # When VEN sets report to 'full' mode (see VEN) the reporting_interval sets the pace of reports
            logger.info(f"VTN.on_register_report(): RealEnergy - sampling_interval={self.sampling_interval} reporting_interval={self.reporting_interval}")
            return callback, self.sampling_interval, self.reporting_interval
        else:
            logger.warning(f"VTN.on_register_report(): measurement={measurement} not handled")
            return None

    # testing EPRI VEN
    async def on_energy_usage_report(self, data, ven_id, resource_id, measurement):
        """
        Callback that receives report data from the VEN and handles it.
        """
        logger.info(f"VTN.on_energy_usage_report(): ven_id={ven_id} resource_id={resource_id} measurement={measurement}\n")
        logger.debug(f"VTN.on_energy_usage_report(): data={data}")

        await OPENADRAPI.send_report(data, ven_id, resource_id, measurement)


    async def on_status_report(self, data, ven_id, resource_id, measurement):
        """
        Callback that receives report data from the VEN and handles it.
        """
        logger.info(f"VTN.on_status_report(): ven_id={ven_id} resource_id={resource_id} measurement={measurement}\n")
        logger.debug(f"VTN.on_status_report(): data={data}")

        await OPENADRAPI.update_device_status(data, ven_id, resource_id, measurement)

    async def on_request_event(self, ven_id, event_id, opt_type):
        """
        Callback that receives a request from a VEN for an Event.
        """
        logger.info(f"VTN.on_request_event(): VEN {ven_id} responded to Event {event_id} with: {opt_type}")

    async def on_event_response(self, ven_id, event_id, opt_type):
        """
        Callback that receives the response from a VEN to an Event.
        """
        logger.info(f"VTN.on_event_response(): VEN {ven_id} responded {opt_type} to event {event_id}")

    def add_event(self, ven_id, signal_name, signal_type, intervals):
        """ Externally accessible method to add event from outside the asyncio event loop"""
        logger.info(f"VTN.add_event() VEN={ven_id} signal_name={signal_name} signal_type={signal_type} \n")
        logger.debug(f"VTN.add_event() VEN={ven_id} signal_name={signal_name} signal_type={signal_type} intervals={intervals}")
        try:
            self.server.add_event(ven_id, signal_name, signal_type, intervals,
                                    market_context=MARKET_CONTEXT,
                                    callback=self.on_event_response)
        except Exception as e:
            logger.warning(f"VTN.add_event(), exception={e}")

    def get_ven_ids(self):
        """provide list of ven IDs"""
        logger.info(f"VTN.get_ven_ids() ven_ids={self._ven_ids}")
        return self._ven_ids

    def start_async(self):
        """Run the server in the Python AsyncIO Event Loop"""
        logger.info("VTN.start_async()")
        try:
            self._loop = asyncio.get_event_loop()
            self._loop.set_debug(1)
            self._loop.create_task(self.server.run())
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"VTN.start_async() async loop error = {e}")
            pass
        finally:
            self._loop.close()

    def start_thread(self):
        """Run the server on the asyncio event loop, in its own thread"""
        logger.info("VTN.start_thread()")
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever).start()
        future = asyncio.run_coroutine_threadsafe(self.server.run(), self._loop)

    def stop(self):
        """Stop the server"""
        logger.info("VTN stop")
        self.server.stop()

def main(argv):
    """VTN main"""
    logger.info("VTN.main()")
    logger.debug(f"Argument List: {str(argv)}")
    reporting_interval = DEFAULT_REPORTING_INTERVAL
    sampling_interval = DEFAULT_SAMPLING_INTERVAL
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
    logger.info(f"VTN.main() reporting_interval={reporting_interval} sampling_interval={sampling_interval} host={host}")

    vtn = VTN(reporting_interval, sampling_interval, host)
    vtn.start_async()

if __name__ == "__main__":
    main(sys.argv[1:])
