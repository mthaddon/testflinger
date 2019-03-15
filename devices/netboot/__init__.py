# Copyright (C) 2016 Canonical
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Netboot support code."""

import logging
import multiprocessing
import yaml

import guacamole

import snappy_device_agents
from devices.netboot.netboot import Netboot
from snappy_device_agents import logmsg

from devices import (Catch,
                     ProvisioningError,
                     RecoveryError,
                     DefaultReserve,
                     DefaultRuntest)

device_name = "netboot"


class provision(guacamole.Command):

    """Tool for provisioning baremetal with a given image."""

    @Catch(RecoveryError, 46)
    def invoked(self, ctx):
        """Method called when the command is invoked."""
        with open(ctx.args.config) as configfile:
            config = yaml.safe_load(configfile)
        snappy_device_agents.configure_logging(config)
        device = Netboot(ctx.args.config)
        image = snappy_device_agents.get_image(ctx.args.job_data)
        if not image:
            raise ProvisioningError('Error downloading image')
        server_ip = snappy_device_agents.get_local_ip_addr()
        test_username = snappy_device_agents.get_test_username(
            ctx.args.job_data)
        test_password = snappy_device_agents.get_test_password(
            ctx.args.job_data)
        logmsg(logging.INFO, "BEGIN provision")
        logmsg(logging.INFO, "Booting Master Image")
        """Initial recovery process
        If the netboot (master) image is already booted and we can get to then
        URL for it, then just continue with provisioning. Otherwise, try to
        force it into the test image first, recopy the ssh keys if necessary,
        reboot if necessary, and get it into the netboot image before going on
        """
        if not device.is_master_image_booted():
            try:
                device.ensure_test_image(test_username, test_password)
                device.ensure_master_image()
            except ProvisioningError:
                raise RecoveryError("Unable to put system in a usable state!")
        q = multiprocessing.Queue()
        file_server = multiprocessing.Process(
            target=snappy_device_agents.serve_file, args=(q, image,))
        file_server.start()
        server_port = q.get()
        logmsg(logging.INFO, "Flashing Test Image")
        device.flash_test_image(server_ip, server_port)
        file_server.terminate()
        logmsg(logging.INFO, "Booting Test Image")
        device.ensure_test_image(test_username, test_password)
        logmsg(logging.INFO, "END provision")

    def register_arguments(self, parser):
        """Method called to customize the argument parser."""
        parser.add_argument('-c', '--config', required=True,
                            help='Config file for this device')
        parser.add_argument('job_data', help='Testflinger json data file')


class DeviceAgent(guacamole.Command):

    """Device agent for Netboot."""

    sub_commands = (
        ('provision', provision),
        ('reserve', DefaultReserve),
        ('runtest', DefaultRuntest),
    )
