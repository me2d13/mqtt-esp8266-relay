import utime, network, gc
import app.secrets as secrets
from network import WLAN
from umqtt.robust import MQTTClient
import ujson
import machine
from app.ota_updater import OTAUpdater

print('Memory free', gc.mem_free())


def main():
    connect_wifi()
    version = check_for_updates()
    context = { 'pin': machine.Pin(secrets.PIN_R, machine.Pin.OUT), 'version': version }
    client = init_mqtt(context)
    while True:
        client.wait_msg()
    client.disconnect()

def check_for_updates():
    print('Checking for updates...')
    otaUpdater = OTAUpdater(secrets.GITHUB_URL, github_src_dir='src', main_dir='app', secrets_file="secrets.py")
    was_installed = False
    version = '?'
    try:
        (was_installed, version) = otaUpdater.install_update_if_available()
    except Exception as e:
        print('Error during update check:', e)
    del(otaUpdater)
    if was_installed:
        print('Update to version {} installed, reboot...'.format(version))
        machine.reset()
        utime.sleep(5)
    else:
        print('Current version {} ok, no new version found'.format(version))
    return version


def connect_wifi():
    sta_if: WLAN = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        while not sta_if.isconnected():
            utime.sleep_ms(100)
    print('network config:', sta_if.ifconfig())


def dispatch_message(topic, msg, context):
    topic = topic.decode("utf-8")
    msg = msg.decode("utf-8")
    print('Received MQTT message at {}'.format(topic), msg)
    try:
        parsed = ujson.loads(msg)
        gc.collect()
        on_parsed_message(parsed, context)
    except ValueError as e:
        print('Json parsing error', e)
        # light.log_function('Json parsing error for ' + msg)

def on_parsed_message(parsed, context):
    if 'status' in parsed:
        if parsed['status'].upper() == 'ON':
            set_pin(context, 1)
        elif parsed['status'].upper() == 'OFF':
            set_pin(context, 0)
        else:
            print('Status {} not recognized'.format(parsed['status']))
    elif 'push' in parsed:
        delay_ms = int(parsed['push'])
        set_pin(context, 1)
        print('Going to sleeping for {}ms'.format(delay_ms))
        utime.sleep_ms(delay_ms)
        set_pin(context, 0)
    else:
        print('Command not recognized {}'.format(parsed))


def set_pin(context, value):
    context['pin'].value(value)
    state_msg = '{{"status": {} }}'.format(value)
    print('Pin set to {}, sending state{}'.format(value, state_msg))
    context["client"].publish(secrets.STATE_TOPIC, state_msg)


def init_mqtt(context):
    def callback_with_context(topic, msg):
        dispatch_message(topic, msg, context)

    def mqtt_log(message):
        client.publish(secrets.LOG_TOPIC, message)

    client = MQTTClient(secrets.MQTT_CLIENT, secrets.MQTT_HOST, secrets.MQTT_PORT)
    context['client'] = client
    client.set_callback(callback_with_context)
    client.connect()
    print('MQTT connected to', secrets.MQTT_HOST)
    client.subscribe(secrets.COMMAND_TOPIC)
    print('MQTT subscribed to', secrets.COMMAND_TOPIC)
    client.publish(secrets.LOG_TOPIC, "Device {} alive with version {}".format(secrets.STATE_TOPIC, context['version']))

    return client
