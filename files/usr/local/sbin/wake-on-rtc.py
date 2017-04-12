#!/usr/bin/python
# --------------------------------------------------------------------------
# Script executed by systemd service for wake-on-rtc.service.
#
# Please edit /etc/wake-on-rtc.conf to configure the script.
#
# Author: Bernhard Bablok
# License: GPL3
#
# Website: https://github.com/bablokb/pi-wake-on-rtc
#
# --------------------------------------------------------------------------

import os, subprocess, sys, syslog, signal
import datetime, re
import ConfigParser

import ds3231

# --- helper functions   ---------------------------------------------------

# --------------------------------------------------------------------------

def write_log(msg):
  global debug
  if debug == '1':
    syslog.syslog(msg)

# --------------------------------------------------------------------------

def get_global(cparser):
  """ return global configurations """
  return (debug,alarm)

# --------------------------------------------------------------------------

def get_config(cparser):
  """ parse configuration """
  global debug
  cfg = {}

  debug = cparser.get('GLOBAL','debug')
  alarm = cparser.getint('GLOBAL','alarm')
  i2c   = cparser.getint('GLOBAL','i2c')
  utc   = cparser.getint('GLOBAL','utc')
  
  boot_hook  = cparser.get('boot','hook_cmd')

  halt_hook   = cparser.get('halt','hook_cmd')
  lead_time   = cparser.get('halt','lead_time')
  set_hwclock = cparser.get('halt','set_hwclock')

  return {'alarm':       alarm,
          'i2c':         i2c,
          'utc':         utc,
          'boot_hook':   boot_hook,
          'halt_hook':   halt_hook,
          'lead_time':   lead_time,
          'set_hwclock': set_hwclock}

# --- convert time-string to datetime-object   -----------------------------

def get_datetime(dtstring):
  if '/' in dtstring:
    format = "%m/%d/%Y %H:%M:%S"
  else:
    format = "%d.%m.%Y %H:%M:%S"

  # add default hour:minutes:secs if not provided
  if ':'  not in dtstring:
    dtstring = dtstring + " 00:00:00"

  # parse string and check if we have six items
  dateParts= re.split('\.|/|:| ',dtstring)
  count = len(dateParts)
  if count < 5 or count > 6:
    raise ValueError()
  elif count == 5:
    dtstring = dtstring + ":00"

  if len(dateParts[2]) == 2:
    format = format.replace('Y','y')

  return datetime.datetime.strptime(dtstring,format)

# --- system startup   -----------------------------------------------------

def process_start():
  """ system startup """
  global config
  write_log("processing system startup")

  # check alarm
  rtc = ds3231.ds3231(config['i2c'],config['utc'])
  (enabled,fired) = rtc.get_alarm_state(alarm)
  mode = "alarm" if enabled and fired else "normal"
  write_log("startup-mode: %s" % mode)

  # create status-file /var/run/wake-on-rtc.status
  with  open("/var/run/wake-on-rtc.status","w") as sfile:
    sfile.write(mode)

  # execute hook-command
  write_log("executing boot-hook %s" % config['boot_hook'])
  proc = subprocess.Popen([config['boot_hook'],mode])
  # configure async operation!

  # clear and disable alarm
  rtc.clear_alarm(alarm)
  rtc.set_alarm(alarm,0)
  write_log("alarm %d cleared and disabled" % alarm)

# --- system shutdown   ----------------------------------------------------

def process_stop():
  """ system shutdown """
  global config
  write_log("processing system shutdown")

  # get next boot-time
  write_log("executing halt-hook %s" % config['halt_hook'])
  proc = subprocess.Popen(config['halt_hook'], stdout=subprocess.PIPE)
  (boot_time,err) = proc.communicate(None)
  #boot_time = proc.stdout.read()
  write_log("raw boot time: %s" % boot_time)
  boot_dt = get_datetime(boot_time)
  write_log("raw boot_dt: %s" % boot_dt)
  
  # set alarm
  rtc = ds3231.ds3231(config['i2c'],config['utc'])
  lead_delta = datetime.timedelta(minutes=config['lead_time'])
  boot_dt = boot_dt - lead_delta
  write_log("calculated boot time: %s" % boot_dt)
  rtc.set_alarm_time(config['alarm'],boot_dt)

  # update hwclock from system-time
  if config['set_hwclock'] == 1:
    rtc.write_system_datetime_now()

    

# --------------------------------------------------------------------------

def signal_handler(_signo, _stack_frame):
  """ signal-handler for cleanup """
  write_log("interrupt %d detected, exiting" % _signo)
  sys.exit(0)

# --- main program   -------------------------------------------------------

syslog.openlog("wake-on-rtc")
parser = ConfigParser.RawConfigParser(
  {'debug': '0',
   'alarm': 1,
   'i2c': 1,
   'utc': 1})
parser.read('/etc/wake-on-rtc.conf')
config = get_config(parser)
write_log("Config: " + str(config))

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

try:
  if len(sys.argv) != 2:
    write_log("missing argument")
  elif sys.argv[1] == "start":
    process_start()
  elif sys.argv[1] == "stop":
    process_stop()
  else:
    write_log("unsupported argument")
except:
  syslog.syslog("Error while executing service: %s" % sys.exc_info()[0])
  raise
