"""API for OPENADR"""

import requests
import json
import logging
import datetime
from enum import Enum
import pytz
import os

logger = logging.getLogger('openadr')

MDM_URL = os.getenv('MDM_URL', 'https://nhectest.stratus.coop/mdm/tools/services/rest/v2/intervaldata?fileName=NiscTest.txt&messageFormat=niscMEPMD01V1');
MDM_AUTH = ('bellawatttest', 'wTkkYBjr1dqP97VyjXR')
# CMEP filename spec: UtilityName_Format_YYYYMMDD_HHMM_REPORTJOBID.dat, eg NHEC_MEPMD01V1_20220315_1415_0000000.dat
MDM_FILENAME_PREFIX = 'NHEC_MEPMD01V1_'
MDM_FILENAME_SUFFIX = '_0000000.dat'

# Localhost assumes API running on same VM/Host. Could be remote
# TER_HOST = 'localhost'
TER_HOST = os.getenv('TER_HOST', '127.0.0.1')
METERS_URL = os.getenv('TER_HOST', '127.0.0.1') + '/meters/' #'http://'+TER_HOST+':80/meters/'
DEVICES_URL = os.getenv('TER_HOST', '127.0.0.1') + '/devices/' #'http://'+TER_HOST+':80/devices/'
LAST_CMEP_FILE = "last_cmep.dat"
MDM_REPORT_ENABLED = os.getenv('MDM_REPORT_ENABLED', False);

"""CMEP Metering Data Type 1 Interval Data"""
class CMEP_DATA:
    def __init__(self):
        self.datetime = None
        self.ProtocolText = 'R'
        self.data = None

class MEPMD01:
    def __init__(self):
        self.RecordType = 'MEPMD01'
        self.RecordVersion = '19970819'
        self.SenderID = 'NHEC'
        self.SenderCustomerID = None
        self.ReceiverID = 'NISCMDM'
        self.RecieverCustomerID = None
        self.TimeStamp = None
        self.MeterID = None
        self.Purpose = 'OK'
        self.Commodity = 'E'
        self.Units = None
        self.CalculationConstant = 1.0
        self.Interval = None
        self.Count = None
        self.Data = []

    def write_csv(self, f):
        self._write_value(f, self.RecordType, ',')
        self._write_value(f, self.RecordVersion, ',')
        self._write_value(f, self.SenderID, ',')
        self._write_value(f, self.SenderCustomerID, ',')
        self._write_value(f, self.ReceiverID, ',')
        self._write_value(f, self.RecieverCustomerID, ',')
        self._write_value(f, self.TimeStamp, ',')
        self._write_value(f, self.MeterID, ',')
        self._write_value(f, self.Purpose, ',')
        self._write_value(f, self.Commodity, ',')
        self._write_value(f, self.Units, ',')
        self._write_value(f, self.CalculationConstant, ',')
        self._write_value(f, self.Interval, ',')
        logger.info(f"write_csv() count={self.Count}")
        self._write_value(f, self.Count, ',')
        for i in range(self.Count):
            self._write_value(f, self.Data[i].datetime, ',')
            self._write_value(f, self.Data[i].ProtocolText, ',')
            if i >= self.Count-1:
               self._write_value(f, self.Data[i].data, '\n')
            else:
               self._write_value(f, self.Data[i].data, ',')

    def _write_value(self, f, v, terminus):
        if type(v) is not str:
            v = str(v)
        f.write(v.encode('ascii'))
        f.write(terminus.encode('ascii'))

class OPENADRAPI:
    """API for OPENADR"""

    async def send_report(data, ven_id, resource_id, measurement):
        """Send report to external billing system"""
        logger.info(f"OPENADRAPI.send_report() ven_id={ven_id}, resource_id={resource_id}, measurement={measurement}")
        logger.debug(f"OPENADRAPI.send_report() data={data}")

        # Find meter data for this device (aka resource_id)
        meter = OPENADRAPI.get_meter(device_id=resource_id)
        if meter is None:
            logger.warning(f"OPENADRAPI.send_report(): resource_id {resource_id} not pre-registered!")
            return None

        # write report to file in ASCII
        fn = MDM_FILENAME_PREFIX+datetime.datetime.utcnow().strftime("%Y%m%d_%H%M")+MDM_FILENAME_SUFFIX
        with open(fn, 'wb') as f:
            logger.info(f"OPENADRAPI.send_report() l={len(data)} filename={fn}")
            # write records
            OPENADRAPI._create_cmep_records(f, meter, data)

        # PUT CMEP file to NISC MDM
        files = {'file': (fn, open(fn, 'rb'), 'application/octet-stream', {'Expires': '0'})}
        if MDM_REPORT_ENABLED:
          response = requests.put(MDM_URL, files=files, auth=MDM_AUTH)
          logger.debug(f"OPENADRAPI.send_report() response.text={response}")
        else:
          logger.debug(f"Skipping report PUT because MDM_REPORT_ENABLED is false")

        # rename latest file for debugging
        if os.path.isfile(LAST_CMEP_FILE):
            os.remove(LAST_CMEP_FILE)
        os.rename(fn, LAST_CMEP_FILE)

    def _create_cmep_records(f, meter, data):
        """Create 4 cmep records (lines) KWH, GKWH, KWHREG, GKWHREG"""
        totalConsumed = totalProduced = 0
        for recordNum in range(4):
            # logger.debug(f"OPENADRAPI._create_cmep_report() meter={meter} mepmd01={mepmd01} data={data}")
            mepmd01 = MEPMD01()
            mepmd01.TimeStamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M")
            mepmd01.MeterID = meter['meter_id']
            if recordNum == 0:
                # create and write record for KWH
                mepmd01.Units = "KWH"
                mepmd01.Interval = 60
                l = len(data)
                mepmd01.Count = l
                for i in range(l):
                    cmep_data = CMEP_DATA()
                    cmep_data.datetime = data[i]['dtstart'].strftime("%Y%m%d%H%M")
                    # kWh records electricity used
                    if data[i]['value'] >= 0:
                        cmep_data.data = data[i]['value']
                    else:
                        cmep_data.data = 0
                    mepmd01.Data.append(cmep_data)
                    totalConsumed += cmep_data.data
            elif recordNum == 1:
                # create and write record for GKWH
                mepmd01.Units = "GKWH"
                mepmd01.Interval = 60
                l = len(data)
                mepmd01.Count = l
                for i in range(l):
                    cmep_data = CMEP_DATA()
                    cmep_data.datetime = data[i]['dtstart'].strftime("%Y%m%d%H%M")
                    # gkWh records electricity produced - indicated by a negative value
                    if data[i]['value'] >= 0:
                        cmep_data.data = 0
                    else:
                        cmep_data.data = abs(data[i]['value'])
                    mepmd01.Data.append(cmep_data)
                    totalProduced += cmep_data.data
            elif recordNum == 2:
                # create and write record for KWHREG
                mepmd01.Units = "KWHREG"
                mepmd01.Interval = 0
                mepmd01.Count = 1
                cmep_data = CMEP_DATA()
                cmep_data.datetime = data[l - 1]['dtstart'].strftime("%Y%m%d%H%M")
                totalConsumed = OPENADRAPI._save_register_data('KWHREG', meter['device_id'], totalConsumed)
                cmep_data.data = totalConsumed
                mepmd01.Data.append(cmep_data)
            else:
                # create and write record for GKWHREG
                mepmd01.Units = "GKWHREG"
                mepmd01.Interval = 0
                mepmd01.Count = 1
                cmep_data = CMEP_DATA()
                cmep_data.datetime = data[l - 1]['dtstart'].strftime("%Y%m%d%H%M")
                totalProduced = OPENADRAPI._save_register_data('GKWHREG', meter['device_id'], totalProduced)
                cmep_data.data = totalProduced
                mepmd01.Data.append(cmep_data)

            mepmd01.write_csv(f)

    def _get_register_data(units, resource_id):
        """determine cumulative usage for a device """
        logger.info(f"OPENADR._get_register_data() units={units} resource_id={resource_id}")

        response = requests.get(DEVICES_URL)
        # response = requests.get(DEVICES_URL_URL, auth=HTTPBasicAuth(DEVICES_URL_USER, DEVICES_URL_PSWD))
        if response.status_code != 200:
            logger.warning(f"OPENADR._get_register_data() GET response.status_code={response.status_code}")
            return None

        devices = json.loads(response.text)
        logger.debug(f"OPENADR._get_register_data() devices={devices}")
        found = False
        for d in devices:
            if d['device_id'] == resource_id:
                found = True
                break

        logger.debug(f"OPENADR._get_register_data() d.registerConsumed={d['registerConsumed']} d.registerProduced={d['registerProduced']}")
        if found:
            if units == 'KWHREG':
                return d['registerConsumed']
            elif units == 'GKWHREG':
                return d['registerProduced']
            else:
                logger.warning(f"OPENADRAPI._get_register_data() invalid units={units}")
        else:
            logger.warning(f"OPENADR._get_register_data() resource_id={resource_id} not found!")
            return None

    def _save_register_data(units, resource_id, usage):
        """update cumulative usage for a device """
        logger.info(f"OPENADR._save_register_data() units={units} resource_id={resource_id} usage={usage}")

        response = requests.get(DEVICES_URL)
        # response = requests.get(DEVICES_URL_URL, auth=HTTPBasicAuth(DEVICES_URL_USER, DEVICES_URL_PSWD))
        if response.status_code != 200:
            logger.warning(f"OPENADR._save_register_data() GET response.status_code={response.status_code}")
            return None

        devices = json.loads(response.text)
        logger.debug(f"OPENADR._save_register_data() devices={devices}")
        found = False
        path = None
        for device in devices:
            logger.info(f"OPENADR._save_register_data() device={device}")
            # find index of existing entry if present
            if device['device_id'] == resource_id:
                path=f"{DEVICES_URL}"+str(device['id'])+"/"
                found = True
                break

        register = 0
        if found:
            if units == 'KWHREG':
                register = float(device['registerConsumed'])
                register += float(usage)
                register = round(register, 2)
                device['registerConsumed'] = str(register)
            elif units == 'GKWHREG':
                register = float(device['registerProduced'])
                register += float(usage)
                register = round(register, 2)
                device['registerProduced'] = str(register)
            else:
                logger.warning(f"OPENADRAPI._save_register_data() invalid units={units}")
        
            logger.debug(f"OPENADR._save_register_data() device.registerConsumed={device['registerConsumed']} device.registerProduced={device['registerProduced']}")

            logger.info(f"OPENADR._save_register_data() PUT url={path} json={json.dumps(device)}")
            response = requests.put(path, json=device)
            if response.status_code != 200:
                logger.warning(f"OPENADR._save_register_data() PUT response.status_code={response.status_code}")
                return None
        else:
            logger.warning(f"OPENADR._save_register_data() resource_id={resource_id} not found!")
            return None

        return register

    def get_meter(ven_id=None, device_id=None):
        # Find meter data for this VEN or device (aka resource_id)
        logger.info(f"OPENADRAPI.get_meter() ven_id={ven_id}, device_id={device_id}")
        meters = OPENADRAPI._get_latest_meters()
        if meters is None:
            logger.warning(f"OPENADRAPI.get_meter() no meters found!")
            return None

        meter = None
        for meter in meters:
            logger.debug(f"OPENADRAPI.get_meter() meter={meter}")
            if ven_id is not None:
              if meter['ven_id'] == ven_id:
                    break
            elif device_id is not None:
                if meter['device_id'] == device_id:
                    break
            else:
                logger.warning("OPENADRAPI.get_meter() neither ven_id or device_id provided")
                return None
            logger.debug(f"OPENADRAPI.get_meter() found meter={meter}")

        if meter == None:
            logger.warning(f"OPENADRAPI.get_meter() no meter found!")

        return meter

    def _get_latest_meters():
        """Traverse meters to find item with lastest creation date"""
        logger.info(f"OPENADR.get_latest_meters()")
        response = requests.get(METERS_URL)
        # response = requests.get(METERS_URL, auth=HTTPBasicAuth(METERS_USER, METERS_PSWD))
        if response.status_code != 200:
            logger.warning(f"OPENADR.get_latest_meters() response.status_code={response.status_code}")
            return None
           
        meters_entries = json.loads(response.text)
        logger.debug(f"OPENADR.get_latest_meters() meters_entries={meters_entries}")
        created = '0'
        latest = None
        for m in meters_entries:
            logger.debug(f"OPENADR.get_latest_meters() m={m}")
            if (m["created"] > created):
                created = m["created"]
                latest = m["meters"]
                logger.debug(f"OPENADR.get_latest_meters() created={created} latest={latest}")

        return (latest)

    async def update_device_status(data, ven_id, resource_id, measurement):
        """update status of device. If device record exists, PUT to update, else POST to create"""
        logger.info(f"OPENADRAPI.update_device_status() ven_id={ven_id}, resource_id={resource_id}, measurement={measurement}")
        logger.debug(f"OPENADRAPI.update_device_status() data={data}")

        # assume just one entry in list of dicts
        statusItem = data[0]
        statusOn = statusItem['resource_status']['online']

        logger.info(f"OPENADRAPI.update_device_status() statusOn={statusOn}")

        # TBD. there may be a way to GET a single record based on device_id, but for now just get and traverse all records
        response = requests.get(DEVICES_URL)
        # response = requests.get(DEVICES_URL_URL, auth=HTTPBasicAuth(DEVICES_URL_USER, DEVICES_URL_PSWD))
        if response.status_code != 200:
            logger.warning(f"OPENADR.update_device_status() GET response.status_code={response.status_code}")
            return None

        devices = json.loads(response.text)
        logger.debug(f"OPENADR.update_device_status() devices={devices}")
        found = False
        path = None
        for d in devices:
            logger.debug(f"OPENADR.update_device_status() d={d}")
            # find index of existing entry if present
            if d['device_id'] == resource_id:
                found = True
                path=f"{DEVICES_URL}"+str(d['id'])+"/"
                break
            
        device = {
            "device_id": resource_id,
            "ven_id": ven_id,
            "statusOn": statusOn
        }

        logger.debug(f"OPENADR.update_device_status() device={device}")
        if found:
            logger.debug(f"OPENADR.update_device_status() PUT url={path} json={json.dumps(device)}")
            response = requests.put(path, json=device)
        else:
            logger.debug(f"OPENADR.update_device_status() POST url={DEVICES_URL} json={json.dumps(device)}")
            response = requests.post(DEVICES_URL, json=device)

        if response.status_code != 200:
            logger.warning(f"OPENADR.update_device_status() PUT/POST response.status_code={response.status_code}")
            return None
