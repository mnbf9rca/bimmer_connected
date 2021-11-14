"""Models the state of a vehicle."""

import datetime
import logging
from enum import Enum
from typing import Dict, List, Tuple

from bimmer_connected.utils import SerializableBaseClass, parse_datetime

_LOGGER = logging.getLogger(__name__)


LIDS = ['driverFront', 'passengerFront', 'driverRear', 'passengerRear', 'hood', 'trunk']

WINDOWS = ['driverFront', 'passengerFront', 'driverRear', 'passengerRear', 'rearWindow', 'sunroof']


class LidState(str, Enum):
    """Possible states of the hatch, trunk, doors, windows, sun roof."""
    CLOSED = 'CLOSED'
    OPEN = 'OPEN'
    OPEN_TILT = 'OPEN_TILT'
    INTERMEDIATE = 'INTERMEDIATE'
    INVALID = 'INVALID'


class LockState(str, Enum):
    """Possible states of the door locks."""
    LOCKED = 'LOCKED'
    SECURED = 'SECURED'
    SELECTIVE_LOCKED = 'SELECTIVE_LOCKED'
    UNLOCKED = 'UNLOCKED'
    UNKNOWN = 'UNKNOWN'


class ConditionBasedServiceStatus(str, Enum):
    """Status of the condition based services."""
    OK = 'OK'
    OVERDUE = 'OVERDUE'
    PENDING = 'PENDING'


class ChargingState(str, Enum):
    """Charging state of electric vehicle."""
    CHARGING = 'CHARGING'
    ERROR = 'ERROR'
    COMPLETE = 'COMPLETE'
    FINISHED_FULLY_CHARGED = 'FINISHED_FULLY_CHARGED'
    FINISHED_NOT_FULL = 'FINISHED_NOT_FULL'
    INVALID = 'INVALID'
    NOT_CHARGING = 'NOT_CHARGING'
    WAITING_FOR_CHARGING = 'WAITING_FOR_CHARGING'


class CheckControlMessage(SerializableBaseClass):
    """Check control message sent from the server.

    This class provides a nicer API than parsing the JSON format directly.
    """

    def __init__(self, ccm_dict: dict):
        self._ccm_dict = ccm_dict

    @property
    def description_long(self) -> str:
        """Long description of the check control message."""
        return self._ccm_dict.get("longDescription")

    @property
    def description_short(self) -> str:
        """Short description of the check control message."""
        return self._ccm_dict.get("title")

    @property
    def ccm_id(self) -> int:
        """id of the check control message."""
        return self._ccm_dict.get("id")

    @property
    def state(self) -> int:
        """state of the check control message."""
        return self._ccm_dict.get("state")


def backend_parameter(func):
    """Decorator for parameters reading data from the backend.

    Errors are handled in a default way.
    """
    def _func_wrapper(self: 'VehicleStatus', *args, **kwargs):
        # pylint: disable=protected-access
        if self.properties is None and self.status:
            raise ValueError('No data available for vehicle status!')
        try:
            return func(self, *args, **kwargs)
        except KeyError:
            _LOGGER.debug('No data available for attribute %s!', str(func))
            return None
        except Exception as ex:
            raise ex
    return _func_wrapper


class VehicleStatus(SerializableBaseClass):  # pylint: disable=too-many-public-methods
    """Models the status of a vehicle."""

    def __init__(self, state: Dict):
        """Constructor."""
        self.status = state["status"]
        self.properties = state["properties"]

    @property
    @backend_parameter
    def timestamp(self) -> datetime.datetime:
        """Get the timestamp when the data was recorded."""
        return max(
            parse_datetime(self.properties['lastUpdatedAt']),
            parse_datetime(self.status['lastUpdatedAt'])
        )

    @property
    @backend_parameter
    def gps_position(self) -> Tuple[float, float]:
        """Get the last known position of the vehicle.

        Returns a tuple of (latitude, longitude).
        This only provides data, if the vehicle tracking is enabled!
        """
        if not self.is_vehicle_tracking_enabled:
            _LOGGER.warning('Vehicle tracking is disabled')
            return None
        if self.is_vehicle_active:
            _LOGGER.warning('Vehicle was moving at last update, no position available')
            return None
        pos = self.properties['vehicleLocation']["coordinates"]
        return float(pos['latitude']), float(pos['longitude'])

    @property
    @backend_parameter
    def gps_heading(self) -> int:
        """Get the last known heading of the vehicle.

        This only provides data, if the vehicle tracking is enabled!
        """
        if not self.is_vehicle_tracking_enabled:
            _LOGGER.warning('Vehicle tracking is disabled')
            return None
        if self.is_vehicle_active:
            _LOGGER.warning('Vehicle was moving at last update, no position available')
            return None
        pos = self.properties['vehicleLocation']
        return int(pos['heading'])

    @property
    @backend_parameter
    def is_vehicle_active(self) -> bool:
        """Check if the vehicle is active/moving.

        If the vehicle was active/moving at the time of the last status update, current position is not available.
        """
        return self.properties['inMotion']

    @property
    @backend_parameter
    def is_vehicle_tracking_enabled(self) -> bool:
        """Check if the position tracking of the vehicle is enabled.

        The server return "OK" if tracking is enabled and "DRIVER_DISABLED" if it is disabled in the vehicle.
        """
        return 'vehicleLocation' in self.properties

    @property
    @backend_parameter
    def mileage(self) -> int:
        """Get the mileage of the vehicle.

        Returns a tuple of (value, unit_of_measurement)
        """
        return (
            self.status['currentMileage']['mileage'],
            self.status['currentMileage']['units']
        )

    @property
    @backend_parameter
    def remaining_range_fuel(self) -> Tuple[int, str]:
        """Get the remaining range of the vehicle on fuel.

        Returns a tuple of (value, unit_of_measurement)
        """
        if "combustionRange" not in self.properties:
            return (None, None)
        return (
            self.properties["combustionRange"]["distance"]["value"],
            self.properties["combustionRange"]["distance"]["units"]
        )

    @property
    @backend_parameter
    def remaining_fuel(self) -> int:
        """Get the remaining fuel of the vehicle.

        Returns a tuple of (value, unit_of_measurement)
        """
        return (
            self.properties['fuelLevel']['value'],
            self.properties['fuelLevel']['units'],
        )

    @property
    @backend_parameter
    def fuel_indicator_count(self) -> int:
        """Gets the number of fuel indicators.

        Can be used to identify REX vehicles if driveTrain == ELECTRIC.
        """
        return len(self.status["fuelIndicators"])

    @property
    @backend_parameter
    def lids(self) -> List['Lid']:
        """Get all lids (doors+hatch+trunk) of the car."""
        result = []
        lids = self.properties["doorsAndWindows"]
        result.extend([Lid(k, v) for k, v in lids.items() if k in ["hood", "trunk"] and v != LidState.INVALID.value])
        result.extend([Lid(k, v) for k, v in lids["doors"].items() if v != LidState.INVALID.value])

        return result

    @property
    def open_lids(self) -> List['Lid']:
        """Get all open lids of the car."""
        return [lid for lid in self.lids if not lid.is_closed]

    @property
    def all_lids_closed(self) -> bool:
        """Check if all lids are closed."""
        return len(list(self.open_lids)) == 0

    @property
    @backend_parameter
    def windows(self) -> List['Window']:
        """Get all windows (doors+sun roof) of the car."""
        result = [
            Window(k, v)
            for k, v in self.properties["doorsAndWindows"].get("windows").items()
            if v != LidState.INVALID.value
        ]
        return result

    @property
    def open_windows(self) -> List['Window']:
        """Get all open windows of the car."""
        return [lid for lid in self.windows if not lid.is_closed]

    @property
    def all_windows_closed(self) -> bool:
        """Check if all windows are closed."""
        return len(self.open_windows) == 0

    @property
    @backend_parameter
    def door_lock_state(self) -> LockState:
        """Get state of the door locks."""
        return LockState(self.status['doorsGeneralState'].upper())

    @property
    @backend_parameter
    def last_update_reason(self) -> str:
        """The reason for the last state update"""
        return self.status['timestampMessage']

    @property
    @backend_parameter
    def last_charging_end_result(self) -> str:
        """Get the last charging end result"""
        return None

    @property
    @backend_parameter
    def connection_status(self) -> str:
        """Get status of the connection"""
        if "chargingState" not in self.properties:
            return None
        return (
            "CONNECTED"
            if self.properties["chargingState"]["isChargerConnected"]
            else "DISCONNECTED"
        )

    @property
    @backend_parameter
    def condition_based_services(self) -> List['ConditionBasedServiceReport']:
        """Get status of the condition based services."""
        return [ConditionBasedServiceReport(s) for s in self.properties['serviceRequired']]

    @property
    def are_all_cbs_ok(self) -> bool:
        """Check if the status of all condition based services is "OK"."""
        for cbs in self.condition_based_services:
            if cbs.state != ConditionBasedServiceStatus.OK:
                return False
        return True

    @property
    @backend_parameter
    def parking_lights(self) -> None:
        """Get status of parking lights.

        :returns None if status is unknown.
        """
        return None  # Not available in My BMW

    @property
    def has_parking_light_state(self) -> bool:
        """Return True if parking light is available."""
        return False  # Not available in My BMW

    @property
    def are_parking_lights_on(self) -> bool:
        """Get status of parking lights.

        :returns None if status is unknown.
        """
        return None  # Not available in My BMW

    @property
    @backend_parameter
    def remaining_range_electric(self) -> Tuple[int, str]:
        """Remaining range on battery, in kilometers."""
        if "electricRange" not in self.properties:
            return None, None
        return (
            self.properties["electricRange"]["distance"]["value"],
            self.properties["electricRange"]["distance"]["units"]
        )

    @property
    @backend_parameter
    def remaining_range_total(self) -> int:
        """Get the total remaining range of the vehicle in kilometers.

        That is electrical range + fuel range.
        """
        # Calculated manually as SERVICE_PROPERTIES.combinedRange == SERVICE_PROPERTIES.combustionRange on fingerprints
        if not self.remaining_range_fuel and not self.remaining_range_electric:
            return None, None
        return (
            ((self.remaining_range_fuel or [0])[0] or 0) + ((self.remaining_range_electric or [0])[0] or 0),
            (self.remaining_range_fuel or self.remaining_range_electric)[1]
        )

    @property
    @backend_parameter
    def max_range_electric(self) -> int:
        """ This can change with driving style and temperature in kilometers."""
        return None  # Not available in My BMW

    @property
    @backend_parameter
    def charging_status(self) -> ChargingState:
        """Charging state of the vehicle."""
        if "chargingState" not in self.properties:
            return None
        return ChargingState(self.properties['chargingState']["state"])

    @property
    @backend_parameter
    def charging_time_remaining(self) -> datetime.timedelta:
        """Get the remaining charging time."""
        return None  # Not available in My BMW

    @property
    @backend_parameter
    def charging_level_hv(self) -> int:
        """State of charge of the high voltage battery in percent."""
        return int(self.properties["electricRangeAndStatus"]["chargePercentage"])

    @property
    @backend_parameter
    def fuel_percent(self) -> int:
        """State of fuel in percent."""
        return int(self.properties['fuelPercentage']["value"])

    @property
    @backend_parameter
    def check_control_messages(self) -> List[CheckControlMessage]:
        """List of check control messages."""
        messages = self.status.get('checkControlMessages', [])
        return [CheckControlMessage(m) for m in messages if m["state"] != "OK"]

    @property
    @backend_parameter
    def has_check_control_messages(self) -> bool:
        """Return true if any check control message is present."""
        return len(self.check_control_messages) > 0


class Lid:  # pylint: disable=too-few-public-methods
    """A lid of the vehicle.

    Lids are: Doors + Trunk + Hatch
    """

    def __init__(self, name: str, state: str):
        #: name of the lid
        self.name = name
        self.state = LidState(state)

    @property
    def is_closed(self) -> bool:
        """Check if the lid is closed."""
        return self.state == LidState.CLOSED


class Window(Lid):  # pylint: disable=too-few-public-methods,no-member
    """A window of the vehicle.

    A window can be a normal window of the car or the sun roof.
    """


class ConditionBasedServiceReport:  # pylint: disable=too-few-public-methods
    """Entry in the list of condition based services."""

    def __init__(self, cbs_data: dict):

        #: date when the service is due
        self.due_date = parse_datetime(cbs_data.get('dateTime'))

        #: status of the service
        self.state = ConditionBasedServiceStatus(cbs_data['status'])

        #: service type
        self.service_type = cbs_data['type']

        #: distance when the service is due
        self.due_distance = None
        if 'distance' in cbs_data:
            self.due_distance = (cbs_data["distance"]['value'], cbs_data["distance"]['units'])

        #: description of the required service
        self.description = None  # Could be retrieved from status.requiredServices if needed
