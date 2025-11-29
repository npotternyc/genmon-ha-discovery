# GenMon Home Assistant Discovery

Python script that provides MQTT discovery for Genmon generator monitors in Home Assistant, including command buttons to control the generator.

## Features

- **Auto-discovery**: Automatically discovers and registers Genmon sensors in Home Assistant
- **Command Buttons**: Provides three buttons in Home Assistant to control the generator:
  - Start Generator
  - Stop Generator
  - Start and Transfer Switch
- **Direct MQTT**: Command buttons publish directly to Genmon's MQTT command topic
- **YAML Configuration**: Optional YAML config file support for easy setup

## Requirements

- Python 3.7+
- MQTT broker (e.g., Home Assistant Mosquitto broker add-on)
- Genmon with MQTT enabled using MQTT broker
- Home Assistant with MQTT integration using MQTT broker

**Note**: External MQTT broker should work, but it has only been tested with add-on

## Configuration

### Option 1: YAML Configuration File (Recommended)

1. Copy the example config file:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Edit `config.yaml` with your settings:
   ```yaml
   # MQTT broker settings
   mqtt:
     host: <your mqtt server>
     port: 1883
     username: <your_username>
     password: <your_password>
     client_id: genmon-ha-discovery

   # Home Assistant settings
   homeassistant:
     discovery_prefix: homeassistant

   # Genmon settings
   genmon:
     topic: generator/#

   # Device information
   device:
     id: Genmon_Generator
     name: Generator
     manufacturer: GenMon
     model: Generator Monitor
     origin: Generator Monitor
   ```

1. Run the script:
   ```bash
   python3 genmon-ha-discovery.py --config config.yaml
   ```

### Option 2: Command Line Arguments

Run the script with command line arguments:

```bash
python3 genmon-ha-discovery.py \
  --mqtt-host homeassistant.local \
  --mqtt-username your_username \
  --mqtt-password your_password \
  --device-name "My Generator"
```

### Option 3: Mixed Configuration

You can combine both methods - YAML file with command line overrides:

```bash
python3 genmon-ha-discovery.py \
  --config config.yaml \
  --mqtt-host different-host.local
```

Command line arguments take precedence over YAML configuration.

## Available Arguments

```
--config, -c              Path to YAML configuration file (optional)
--mqtt-host              MQTT broker host
--mqtt-port              MQTT broker port (default: 1883)
--mqtt-username          MQTT username
--mqtt-password          MQTT password
--mqtt-client-id         MQTT client ID
--discovery-prefix       Home Assistant discovery prefix (default: homeassistant)
--genmon-topic           GenMon MQTT topic to subscribe to (default: generator/#)
--device-id              Device ID (default: Genmon_Generator)
--device-name            Device name (default: Generator)
--device-manufacturer    Device manufacturer (default: GenMon)
--device-model           Device model (default: Generator Monitor)
--ha-origin              Home Assistant origin identifier (default: Generator Monitor)
```

## How It Works

1. **Discovery**: The script subscribes to Genmon's MQTT topics and automatically creates Home Assistant entities as it receives data
2. **Command Buttons**: Three button entities are created in Home Assistant that publish directly to `generator/command`:
   - `generator: start` - Starts the generator
   - `generator: stop` - Stops the generator
   - `generator: starttransfer` - Starts generator and engages transfer switch
3. **Sensors**: All Genmon data points are automatically discovered and registered as sensors with appropriate units and device classes

## Troubleshooting

- **Connection refused**: Ensure MQTT broker is running and accessible
- **Not authorized**: Check MQTT username and password
- **No entities appearing**: Verify Genmon is publishing to MQTT topics
- **Commands not working**: Ensure Genmon has remote commands enabled

## License

MIT License

## Credits

- [Genmon](https://github.com/jgyates/genmon) - Generator monitoring software
- Uses Genmon's remote command API for generator control
