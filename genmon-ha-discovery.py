#!/usr/bin/env python3
import json
import time
import paho.mqtt.client as mqtt
import argparse
import logging
import re
import datetime
from typing import Dict, Any, Optional, Tuple, Union

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('genmon-ha-discovery')

class GenmonHADiscovery:
    def __init__(
        self,
        mqtt_host: Optional[str] = "localhost",
        mqtt_port: Optional[int] = 1883,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        mqtt_client_id: Optional[str] = "genmon-ha-discovery",
        mqtt_discovery_prefix: Optional[str] = "homeassistant",
        mqtt_genmon_topic: Optional[str] = "generator/#",
        ha_device_id: Optional[str] = "Genmon_Generator",
        ha_device_name: Optional[str] = "Generator",
        ha_device_manufacturer: Optional[str] = "GenMon",
        ha_device_model: Optional[str] = "Generator Monitor",
        ha_origin: Optional[str] = "Generator Monitor",
    ):
        # MQTT settings
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.mqtt_client_id = mqtt_client_id
        self.mqtt_discovery_prefix = mqtt_discovery_prefix
        self.mqtt_genmon_topic = mqtt_genmon_topic
        
        # Home Assistant device info
        self.ha_device_id = ha_device_id
        self.ha_device_name = ha_device_name
        self.ha_device_manufacturer = ha_device_manufacturer
        self.ha_device_model = ha_device_model
        self.ha_serial_number = "Undefined"
        self.ha_sw_version = "Undefined"
        self.ha_origin = ha_origin
        self.ha_origin_version = "Undefined"
        self.ha_origin_support_url = "https://github.com/jgyates/genmon"

        # MQTT client setup
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        if mqtt_client_id:
            self.client._client_id = mqtt_client_id.encode()
        if mqtt_username and mqtt_password:
            self.client.username_pw_set(mqtt_username, mqtt_password)
        
        # Setup callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Track registered entities
        self.registered_entities = set()
    
    def start(self):
        """Connect to MQTT broker and start the event loop"""
        try:
            # Use default port if not provided
            mqtt_port = self.mqtt_port if self.mqtt_port is not None else 1883
            mqtt_host = self.mqtt_host if self.mqtt_host is not None else "localhost"
            
            logger.info(f"Connecting to MQTT broker at {mqtt_host}:{mqtt_port}")
            self.client.connect(mqtt_host, mqtt_port, 60)
            self.client.loop_start()
            
            # Wait for the client to connect
            time.sleep(2)
            
            # Run the main loop
            self._main_loop()
            
        except Exception as e:
            logger.error(f"Error connecting to MQTT: {e}")
            return
    
    def stop(self):
        """Disconnect from MQTT broker and stop the event loop"""
        self.client.loop_stop()
        self.client.disconnect()
    
    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback when the client connects to the MQTT broker"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to genmon topics
            self.client.subscribe(self.mqtt_genmon_topic)
            logger.info(f"Subscribed to {self.mqtt_genmon_topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker with code {rc}")
    
    def on_message(self, client, userdata, msg):
        """Callback when a message is received from the MQTT broker"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logger.debug(f"Received message on topic {topic}: {payload}")
            
            # Get topic prefix from the subscription topic
            # Default to 'generator' if mqtt_genmon_topic is None
            topic_prefix = "generator"
            if self.mqtt_genmon_topic:
                topic_parts = self.mqtt_genmon_topic.split('/')
                if topic_parts:
                    topic_prefix = topic_parts[0]
            
            # Process message from GenMon
            if topic.startswith(f"{topic_prefix}/"):
                self._process_genmon_message(topic, payload)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _get_value_template_and_unit(self, payload: str) -> Tuple[str, Optional[str]]:
        """
        Generate an appropriate value template and unit for the payload format
        
        Args:
            payload: The raw payload string from MQTT
            
        Returns:
            Tuple of (value_template, unit) where value_template is a Jinja2 template for HA
        """
        # Check if the payload is JSON format
        try:
            data = json.loads(payload)
            if isinstance(data, dict) and "value" in data:
                unit = data.get("unit", None)
                # JSON value template
                return "{{ value_json.value }}", unit
        except json.JSONDecodeError:
            pass
        
        # Check for date format
        date_match = re.match(r".*?(\d{1,2}/\d{1,2}/\d{4})", payload)
        if date_match:
            # Extract date with regex
            pattern = r".*?(\\d{1,2}/\\d{1,2}/\\d{4})"
            date_template = """{% set date_match = value | regex_findall('""" + pattern + """') %}
                           {% if date_match %}
                             {% set date_str = date_match[0] %}
                             {% set date_parts = date_str.split('/') %}
                             {{ date_parts[2] ~ '-' ~ '%02d' | format(date_parts[0] | int) ~ '-' ~ '%02d' | format(date_parts[1] | int) }}
                           {% else %}
                             {{ value }}
                           {% endif %}"""
            return date_template.strip(), None
        
        # Check for value with units
        value_unit_match = re.match(r".*?\s*(\d+\.?\d*)\s*([a-zA-Z%]+)$", payload)
        if value_unit_match:
            unit = value_unit_match.group(2)
            # Extract numeric value with regex
            pattern = r".*?(\\d+\\.?\\d*)\\s*[a-zA-Z%]+$"
            return "{{ value | regex_findall('" + pattern + "') | first }}", unit
        
        # For key-value format (e.g., "Battery Check Due: 12/29/2025")
        if ":" in payload:
            return "{{ value.split(': ')[1] }}", None
        
        # Default template (no transformation)
        return "{{ value }}", None
    
    def _process_genmon_message(self, topic: str, payload: str):
        """Process a message from GenMon and create/update HA entities"""
        try:
            # Extract entity name from topic
            # Example topic: genmon/status/state or genmon/status/runtime/total
            parts = topic.split('/')
            if len(parts) < 3:
                return
            
            category = parts[1]  # 'status', 'maintenance', etc.
            # Concatenate all parts after and including the 2nd part
            entity_name = '_'.join(parts[2:])
            
            # Determine entity type (sensor, binary_sensor, etc.)
            entity_type = "sensor"  # Default
            
            if entity_name in ['state', 'switch_state']:
                entity_type = "binary_sensor"
            elif entity_name in ['command']:
                entity_type = "switch"
            
            # Create unique ID and topic ID for this entity
            device_id = self.ha_device_id if self.ha_device_id else "genmon_generator"
            # Capitalize each word and replace spaces with underscores
            formatted_name = '_'.join(word.capitalize() for word in entity_name.replace('_', ' ').split())
            unique_id = f"{device_id}_{category.capitalize()}_{formatted_name}"
            object_id = f"{category.capitalize()}_{formatted_name}"

            # Set device info from message if relevant
            if "Controller_Detected" in formatted_name:
                self.ha_device_model = payload
                return
            elif "Generator_Serial_Number" in formatted_name:
                self.ha_serial_number = payload
                return
            elif "Firmware_Version" in formatted_name:
                self.ha_sw_version = payload
            
            # Set up device info (same for all entities)
            device_info = {
                "identifiers": [device_id],
                "name": self.ha_device_name,
                "manufacturer": self.ha_device_manufacturer,
                "model": self.ha_device_model,
                "serial_number": self.ha_serial_number,
                "sw_version": self.ha_sw_version
            }

            #Set up origin info (same for all entities)
            origin_info = {
                "name": self.ha_origin,
                "sw_version": self.ha_origin_version,
                "support_url": self.ha_origin_support_url
            } 
            
            # Get value template and unit based on payload format
            value_template, unit = self._get_value_template_and_unit(payload)
            
            # Register entity if not already registered
            if unique_id not in self.registered_entities:
                # Create a discovery config for this entity
                self._register_ha_entity(entity_type, category, entity_name, unique_id, object_id, device_info, origin_info, topic, value_template, unit)
                self.registered_entities.add(unique_id)
            
        except Exception as e:
            logger.error(f"Error processing GenMon message: {e}")
    
    def _register_ha_entity(self, entity_type: str, category: str, entity_name: str, 
                           unique_id: str, object_id: str, device_info: Dict[str, Any], origin_info: Dict[str, Any],
                           state_topic: str, value_template: str, unit: Optional[str] = None):
        """Register an entity with Home Assistant discovery"""
        # Base configuration for all entity types
        config = {
            "name": ' '.join(word.capitalize() for word in f"{category} {entity_name.replace('_', ' ')}".split()),
            "unique_id": unique_id,
            "state_topic": state_topic,  # Use the original MQTT topic
            "value_template": value_template,
            "device": device_info,
            "origin": origin_info,
            "object_id": object_id 
        }
        
        # Add entity-specific configuration
        if entity_type == "binary_sensor":
            config.update({
                "payload_on": "ON",
                "payload_off": "OFF"
            })
        elif entity_type == "switch":
            config.update({
                "command_topic": f"{self.mqtt_discovery_prefix}/{entity_type}/{self.ha_device_id}/{unique_id}/set",
                "payload_on": "ON",
                "payload_off": "OFF"
            })
        elif entity_type == "sensor":
            # For sensors, add device class based on content
            if any(x in entity_name.lower() for x in ["due", "next", "date"]):
                config.update({
                    "device_class": "date"
                })
            elif any(x in entity_name.lower() for x in ["runtime", "hours", "run_hours"]):
                config.update({
                    "device_class": "duration",
                    "state_class": "total_increasing"
                })
            
            # Add unit of measurement if available
            if unit:
                config["unit_of_measurement"] = unit
        
        # Publish discovery config
        discovery_topic = f"{self.mqtt_discovery_prefix}/{entity_type}/{self.ha_device_id}/{unique_id}/config"
        self.client.publish(discovery_topic, json.dumps(config), retain=True)
        logger.info(f"Registered {entity_type}: {unique_id}")
    
    def _main_loop(self):
        """Main processing loop"""
        try:
            logger.info("GenMon HA Discovery running. Press Ctrl+C to exit.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.stop()

def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(description='GenMon Home Assistant Discovery')
    
    # MQTT connection arguments
    parser.add_argument('--mqtt-host', help='MQTT broker host')
    parser.add_argument('--mqtt-port', type=int, help='MQTT broker port')
    parser.add_argument('--mqtt-username', help='MQTT username')
    parser.add_argument('--mqtt-password', help='MQTT password')
    parser.add_argument('--mqtt-client-id', help='MQTT client ID')
    
    # Home Assistant arguments
    parser.add_argument('--discovery-prefix', help='Home Assistant discovery prefix')
    parser.add_argument('--genmon-topic', help='GenMon MQTT topic to subscribe to')
    
    # Device info arguments
    parser.add_argument('--device-id', help='Device ID')
    parser.add_argument('--device-name', help='Device name')
    parser.add_argument('--device-manufacturer', help='Device manufacturer')
    parser.add_argument('--device-model', help='Device model')
    parser.add_argument('--ha-origin', help='Home Assistant origin identifier')
    
    args = parser.parse_args()
    
    # Create kwargs dictionary with only defined arguments
    kwargs = {}
    if args.mqtt_host is not None:
        kwargs['mqtt_host'] = args.mqtt_host
    if args.mqtt_port is not None:
        kwargs['mqtt_port'] = args.mqtt_port
    if args.mqtt_username is not None:
        kwargs['mqtt_username'] = args.mqtt_username
    if args.mqtt_password is not None:
        kwargs['mqtt_password'] = args.mqtt_password
    if args.mqtt_client_id is not None:
        kwargs['mqtt_client_id'] = args.mqtt_client_id
    if args.discovery_prefix is not None:
        kwargs['mqtt_discovery_prefix'] = args.discovery_prefix
    if args.genmon_topic is not None:
        kwargs['mqtt_genmon_topic'] = args.genmon_topic
    if args.device_id is not None:
        kwargs['ha_device_id'] = args.device_id
    if args.device_name is not None:
        kwargs['ha_device_name'] = args.device_name
    if args.device_manufacturer is not None:
        kwargs['ha_device_manufacturer'] = args.device_manufacturer
    if args.device_model is not None:
        kwargs['ha_device_model'] = args.device_model
    if args.ha_origin is not None:
        kwargs['ha_origin'] = args.ha_origin
    
    # Create discovery instance with only defined arguments
    discovery = GenmonHADiscovery(**kwargs)
    
    discovery.start()

if __name__ == "__main__":
    main()