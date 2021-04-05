# mqtt-esp8266-relay
Relay controlled by mqtt message

## Supported json payloads
    {"status":"ON"}
    {"status":"OFF"}
    {"push":500}
Push parameter is in ms - how long keep pin at 1

## Install notes
Some code snippets I use during development

    esptool.py --port COM7 --baud 460800 write_flash --flash_size=detect 0 /d/Temp/esp8266-20210202-v1.14.bin

    rshell
    connect serial COM7
    rsync src /pyboard
    repl

    mosquitto_pub -t "/devices/relay/door/set" -m '{"push":500}'
