from django.test import TestCase
from unittest import mock
from .openadr import OPENADR
from openadr.vtn import VTN
from datetime import datetime, timedelta, timezone
from openadr.api import OPENADRAPI

class OpenADRTestCase(TestCase):
  def setUp(self):
    pass


  @mock.patch('openadr.openadr.VTN')
  def test_add_event(self, mock_vtn):
    mock_vtn_instance = mock.Mock()
    mock_vtn.return_value = mock_vtn_instance

    intervals = []
    openadr = OPENADR(60,60,'0.0.0.0').add_event(1, intervals)


    mock_vtn.assert_called_with(60, 60, "0.0.0.0")
    mock_vtn_instance.add_event.assert_called_once_with(
      ven_id=1,
      intervals=intervals,
      signal_name=mock.ANY,
      signal_type=mock.ANY,
    )


  @mock.patch('openadr.openadr.requests')
  @mock.patch('openadr.openadr.VTN')
  def test_event_poll(self, mock_vtn, mock_requests):
    mock_vtn_instance = mock.Mock()
    mock_vtn.return_value = mock_vtn_instance

    mock_vtn_instance.get_ven_ids.return_value = [1]

    mock_response = mock.Mock()
    mock_requests.get.return_value = mock_response

    mock_response.status_code = 200
    mock_response.json.return_value = {
        "date":"2022-03-07",
        "prices": [
            {"datetime":"2022-03-08T0:0:0+0000","price":"12.34"},
            {"datetime":"2022-03-08T0:1:0+0000","price":"23.45"},
            {"datetime":"2022-03-08T0:2:0+0000","price":"34.56"}
        ]
    }

    openadr = OPENADR(60,60,'0.0.0.0')

    openadr.event_poll()
    openadr.event_poll()

    mock_vtn_instance.add_event.assert_called_once_with(
      ven_id=1,
      intervals=mock.ANY,
      signal_name=mock.ANY,
      signal_type=mock.ANY,
    )

  @mock.patch('openadr.openadr.requests')
  @mock.patch('openadr.openadr.VTN')
  def test_signal_duration_set_60_min(self, mock_vtn, mock_requests):
    mock_vtn_instance = mock.Mock()
    mock_vtn.return_value = mock_vtn_instance

    mock_vtn_instance.get_ven_ids.return_value = [1]

    mock_response = mock.Mock()
    mock_requests.get.return_value = mock_response

    mock_response.status_code = 200
    mock_response.json.return_value = {
        "date":"2022-03-07",
        "prices": [
            {"datetime":"2022-03-08T0:0:0+0000","price":"12.34"},
            {"datetime":"2022-03-08T0:1:0+0000","price":"23.45"},
            {"datetime":"2022-03-08T0:2:0+0000","price":"34.56"}
        ]
    }


    intervals = [
      {
        'dtstart':  datetime(2022, 3, 8, 0, 0, tzinfo=timezone.utc),
        'duration': timedelta(minutes=60),
        'signal_payload': 12.34
      },
      {
        'dtstart': datetime(2022, 3, 8, 0, 1, tzinfo=timezone.utc),
        'duration': timedelta(minutes=60),
        'signal_payload': 23.45
      },
      {
        'dtstart': datetime(2022, 3, 8, 0, 2, tzinfo=timezone.utc),
        'duration': timedelta(minutes=60),
        'signal_payload': 34.56
      }
    ]

    openadr = OPENADR(60,60,'0.0.0.0')

    openadr.event_poll()

    mock_vtn_instance.add_event.assert_called_once_with(
      ven_id=1,
      intervals=intervals,
      signal_name=mock.ANY,
      signal_type=mock.ANY,
    )

  @mock.patch('openadr.openadr.requests')
  @mock.patch('openadr.api.OPENADRAPI.send_report')
  async def test_usage_report_sends_report(self, mock_send_report, mock_requests):
    mock_data = {}
    ven_id = "my_ven"
    resource_id = "my_unique_battery"
    measurement = "RealEnergy"

    await VTN({}, {}, 'http://127.0.0.1/meters/').on_energy_usage_report(
      mock_data,
      ven_id,
      resource_id,
      measurement
    )

    mock_send_report.assert_called_once_with(
      mock_data,
      ven_id,
      resource_id,
      measurement
    )
