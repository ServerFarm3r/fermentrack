from __future__ import unicode_literals

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

import requests
import logging

import json

from app.models import BrewPiDevice
from gravity.models import GravitySensor


class GenericPushTarget(models.Model):
    class Meta:
        verbose_name = "Generic Push Target"
        verbose_name_plural = "Generic Push Targets"

    SENSOR_SELECT_ALL = "all"
    SENSOR_SELECT_LIST = "list"
    SENSOR_SELECT_NONE = "none"

    SENSOR_SELECT_CHOICES = (
        SENSOR_SELECT_ALL, "All Sensors/Devices",
        SENSOR_SELECT_LIST, "Specific Sensors/Devices",
        SENSOR_SELECT_NONE, "Nothing of this type",
    )

    SENSOR_PUSH_HTTP = "http"
    SENSOR_PUSH_TCP = "tcp"

    SENSOR_PUSH_CHOICES = (
        SENSOR_PUSH_HTTP, "HTTP/HTTPS",
        SENSOR_PUSH_TCP, "TCP (Telnet/Socket)",
    )

    STATUS_ACTIVE = 'active'
    STATUS_DISABLED = 'disabled'

    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_DISABLED, 'Disabled'),
    )

    DATA_FORMAT_GENERIC = 'generic'
    DATA_FORMAT_TILTBRIDGE = 'tiltbridge'

    DATA_FORMAT_CHOICES = (
        (DATA_FORMAT_TILTBRIDGE, 'TiltBridge Device'),
        (DATA_FORMAT_GENERIC, 'All Data (Generic)'),
    )

    PUSH_FREQUENCY_CHOICES = (
        (5,     '5 seconds'),
        (10,    '10 seconds'),
        (15,    '15 seconds'),
        (30,    '30 seconds'),
        (60,    '1 minute'),
        (60*2,  '2 minutes'),
        (60*5,  '5 minutes'),
        (60*10, '10 minutes'),
        (60*15, '15 minutes'),
        (60*30, '30 minutes'),
        (60*60, '1 hour'),
    )

    name = models.CharField(max_length=48, help_text="Unique name for this push target", unique=True)
    status = models.CharField(max_length=24, help_text="Status of this push target", choices=STATUS_CHOICES,
                              default=STATUS_ACTIVE)
    push_frequency = models.IntegerField(choices=PUSH_FREQUENCY_CHOICES, default=60*15,
                                         help_text="How often to push data to the target")
    api_key = models.CharField(max_length=256, help_text="API key required by the push target (if any)")

    brewpi_push_selection = models.CharField(max_length=12, choices=SENSOR_SELECT_CHOICES, default=SENSOR_SELECT_ALL,
                                             help_text="How the BrewPi devices to push are selected")
    brewpi_to_push = models.ManyToManyField(to=BrewPiDevice, related_name="push_targets",
                                            help_text="BrewPi Devices to push (ignored if 'all' devices selected)")

    gravity_push_selection = models.CharField(max_length=12, choices=SENSOR_SELECT_CHOICES, default=SENSOR_SELECT_ALL,
                                              help_text="How the gravity sensors to push are selected")
    gravity_sensors_to_push = models.ManyToManyField(to=GravitySensor, related_name="push_targets",
                                                     help_text="Gravity Sensors to push (ignored if 'all' "
                                                               "sensors selected)")

    target_type = models.CharField(max_length=24, default=SENSOR_PUSH_HTTP, choices=SENSOR_PUSH_CHOICES,
                                   help_text="Protocol to use to connect to the push target")
    target_host = models.CharField(max_length=256, default="http://127.0.0.1/",
                                   help_text="The URL to push to (for HTTP/HTTPS) or hostname/IP address (for TCP)")
    target_port = models.IntegerField(default=80, validators=[MinValueValidator(10,"Port must be 10 or higher"),
                                                               MaxValueValidator(65535, "Port must be 65535 or lower")],
                                     help_text="The port to use (not used for HTTP/HTTPS)")

    data_format = models.CharField(max_length=24, help_text="The data format to send to the push target",
                                   choices=DATA_FORMAT_CHOICES, default=DATA_FORMAT_GENERIC)

    def data_to_push(self):
        if self.brewpi_push_selection == GenericPushTarget.SENSOR_SELECT_ALL:
            # TODO - Determine if this should actually be all devices, or just active ones (& update descriptions above as necessary)
            brewpi_to_send = BrewPiDevice.objects.all()
        elif self.brewpi_push_selection == GenericPushTarget.SENSOR_SELECT_LIST:
            brewpi_to_send = self.brewpi_to_push.all()
        else:
            # Either SENSOR_SELECT_NONE or not implemented yet
            brewpi_to_send = None

        if self.gravity_push_selection == GenericPushTarget.SENSOR_SELECT_ALL:
            # TODO - Determine if this should actually be all devices, or just active ones (& update descriptions above as necessary)
            grav_sensors_to_send = GravitySensor.objects.all()
        elif self.gravity_push_selection == GenericPushTarget.SENSOR_SELECT_LIST:
            grav_sensors_to_send = self.gravity_sensors_to_push.all()
        else:
            grav_sensors_to_send = None

        # At this point we've obtained the list of objects to send - now we just need to format them.
        string_to_send = ""  # This is what ultimately needs to be populated.
        if self.data_format == self.DATA_FORMAT_TILTBRIDGE:
            to_send = {'api_key': self.api_key, 'brewpi': []}
            for brewpi in brewpi_to_send:
                device_info = brewpi.get_dashpanel_info()

                to_send['brewpi'].append({
                    'name': brewpi.device_name,
                    'temp_format': brewpi.temp_format,
                    'beer_temp':  device_info['BeerTemp'],
                    'fridge_temp': device_info['FridgeTemp'],
                    'gravity': '-.---',  # TODO - Actually make gravity readings work here
                })
            string_to_send = json.dumps(to_send)

        elif self.data_format == self.DATA_FORMAT_GENERIC:
            to_send = {'api_key': self.api_key, 'brewpi': [], 'gravity_sensors': []}
            for brewpi in brewpi_to_send:
                device_info = brewpi.get_dashpanel_info()

                to_send['brewpi'].append({
                    'name': brewpi.device_name,
                    'temp_format': brewpi.temp_format,
                    'beer_temp':  device_info['BeerTemp'],
                    'fridge_temp': device_info['FridgeTemp'],
                    'room_temp': device_info['RoomTemp'],
                    'control_mode': device_info['Mode'],  # TODO - Determine if we want the raw or verbose device mode
                    'gravity': '-.---',  # TODO - Actually make gravity readings work here
                })

            for sensor in grav_sensors_to_send:
                latest_log_point = sensor.retrieve_latest_point()

                grav_dict = {
                    'name': sensor.name,
                    'temp_format': sensor.temp_format,
                    'sensor_type': sensor.sensor_type,
                    'status': sensor.status,
                }

                if latest_log_point is None:
                    # There is no latest log point on redis - default to None
                    grav_dict['gravity'] = None
                    grav_dict['temp'] = None
                    grav_dict['temp_format'] = None
                else:
                    grav_dict['gravity'] = latest_log_point.gravity
                    grav_dict['temp'] = latest_log_point.temp
                    grav_dict['temp_format'] = latest_log_point.temp_format

                to_send['gravity_sensors'].append(grav_dict)

            string_to_send = json.dumps(to_send)
        # We've got the data (in a json'ed string) - lets send it
        return string_to_send

    def send_data(self):
        json_data = self.data_to_push()

        if len(json_data) <= 0:
            # There was no data to push - do nothing.
            return False

        if self.target_type == self.SENSOR_PUSH_HTTP:
            r = requests.post(self.target_host, data={'api_key': self.api_key, 'json_data': json_data})
            return True  # TODO - Check if the post actually succeeded & react accordingly
        elif self.target_type == self.SENSOR_PUSH_TCP:
            # TODO - Push to a socket endpoint
            raise NotImplemented
        else:
            raise NotImplemented

        return False  # Should never get here, but just in case something changes later
