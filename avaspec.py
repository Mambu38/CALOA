﻿import sys
import ctypes
import ctypes.wintypes
import struct
from PyQt5.QtCore import *

AVS_SERIAL_LEN = 10
USER_ID_LEN = 64
WM_MEAS_READY = 0x8001
AVS_SATURATION_VALUE = 16383

dev_handle = 0
pixels = 4096
spectraldata = [0.0] * 4096


#####
# EXCEPTION CLASS
#####

class c_AVA_Exceptions(Exception):

    AVA_EXCEPTION_CODES = {
            -1: ("ERR_INVALID_PARAMETER",
                 "Function called with invalid parameter value"),
            -2: ("ERR_OPERATION_NOT_SUPPORTED",
                 ""),
            -3: ("ERR_DEVICE_NOT_FOUND",
                 "Opening communication failed or time-out occurs."),
            -4: ("ERR_INVALID_DEVICE_ID",
                 "AvsHandle is unknown in the DLL."),
            -5: ("ERR_OPERATION_PENDING",
                 "Function is called while result of previous call to"
                 " AVS_Measure is not received yet."),
            -6: ("ERR_TIMEOUT",
                 "No anwer received from device."),
            -7: ("Reserved", ""),
            -8: ("ERR_INVALID_MEAS_DATA",
                 "Not measure data is received at the point AVS_GetScopeData"
                 " is called."),
            -9: ("ERR_INVALID_SIZE",
                 "Allocated buffer size is too small."),
            -10: ("ERR_INVALID_PIXEL_RANGE",
                  "Measurement preparation failed because pixel range"
                  " is invalid."),
            -11: ("ERR_INVALID_INT_TIME",
                  "Measurement preparation failed because integration time"
                  " is invalid."),
            -12: ("ERR_INVALID_COMBINATION",
                  "Measurement preparation failed because of an invalid"
                  " combination of parameters."),
            -13: ("Reserved", ""),
            -14: ("ERR_NO_MEAS_BUFFER_AVAIL",
                  "Measurement preparation failed because no measurement"
                  " buffers available."),
            -15: ("ERR_UNKNOWN",
                  "Unknown error reason received from spectrometer."),
            -16: ("ERR_COMMUNICATION",
                  "Error in communication occurred."),
            -17: ("ERR_NO_SPECTRA_IN_RAM",
                  "No more spectra available in RAM, all read or measurement"
                  " not started yet."),
            -18: ("ERR_INVALID_DLL_VERSION",
                  "DLL version information could mot be retrieved."),
            -19: ("ERR_NO_MEMORY",
                  "Memory allocation error in the DLL."),
            -20: ("ERR_DLL_INITIALISATION",
                  "Function called before AVS_Init is called."),
            -21: ("ERR_INVALID_STATE",
                  "Function failed because AvaSpec is in wrong state."),
            -22: ("ERR_INVALID_REPLY",
                  "Reply is not a recognized protocol message."),
            -100: ("ERR_INVALID_PARAMETER_NR_PIXEL",
                   "NrOfPixel in Device data incorrect."),
            -101: ("ERR_INVALID_PARAMETER_ADC_GAIN",
                   "Gain Setting Out of Range."),
            -102: ("ERR_INVALID_PARAMETER_ADC_OFFSET",
                   "OffSet Setting Out of Range."),
            -110: ("ERR_INVALID_MEASPARAM_AVG_SAT2",
                   "Use of saturation detection level 2 is not compatible"
                   " with the averaging function."),
            -111: ("ERR_INVALID_MEASPARAM_AVD_RAM",
                   "Use of Averaging is not compatible with StoreToRAM"
                   " function."),
            -112: ("ERR_INVALID_MEASPARAM_SYNC_RAM",
                   "Use of Synchronize setting is not compatible with"
                   " StoreToRAM function"),
            -113: ("ERR_INVALID_MEASPARAM_LEVEL_RAM",
                   "Use of Level Triggering is not compatible with"
                   " StoreToRAM function."),
            -114: ("ERR_INVALID_MASPARAM_SAT2_RAM",
                   "Use of Saturation Detection Level 2 is not compatible"
                   " with the StoreToRAM function."),
            -115: ("ERR_INVALID_MEASPARAM_FWVER_RAM",
                   "The StoreToRAM function is only supported with firmware"
                   " version 0.20.0.0 or later."),
            -116: ("ERR_INVALID_MEASPARAM_DYNDARK",
                   "Dynamic Dark Correction not supported."),
            -120: ("ERR_NOT_SUPPORTED_BY_SENSOR_TYPE",
                   "Use of AVS_SetSensitivityMode not supported by"
                   " detector type."),
            -121: ("ERR_NOT_SUPPORTED_BY_FW_VER",
                   "Use of AVS_SetSensitivityMode not supported by"
                   " firmware version."),
            -122: ("ERR_NOT_SUPPORTED_BY_FPGA_VER",
                   "use of AVS_SetSensitivityMode not supported by"
                   " FPGA version."),
            -140: ("ERR_SL_CALIBRATION_NOT_IN_RANGE",
                   "Spectrometer was not calibrated for stray light"
                   " correction."),
            -141: ("ERR_SL_STARTPIXEL_NOT_IN_RANGE",
                   "Incorrect start pixel found in EEProm."),
            -142: ("ERR_SL_ENDPIXEL_OUT_OF_RANGE",
                   "Incorrect end pixel found in EEProm."),
            -143: ("ERR_SL_STARTPIX_GT_ENDPIX",
                   "Incorrect start or end pixel found in EEProm."),
            -144: ("ERR_SL_MFACTOR_OUT_OF_RANGE",
                   "Factor should be in range 0.0 - 4.0.")
            }

    def __init__(self, P_codeNbr):

        self.code_nbr = P_codeNbr

    def __str__(self):

        return "\n".join(self.AVA_EXCEPTION_CODES[self.code_nbr])

def _check_error(result, func, arguments):
    """
    Method used to check errors.
    See ctypes manual class ctypes._FuncPtr.errcheck for further
    information.
    """

    if result < 0:
        raise c_AVA_Exceptions(result)
    return arguments


#####
# Usefull classes
#####

class AvsIdentityType(ctypes.Structure):
  _pack_ = 1
  _fields_ = [("m_aSerialId", ctypes.c_char * AVS_SERIAL_LEN),
              ("m_aUserFriendlyId", ctypes.c_char * USER_ID_LEN),
              ("m_Status", ctypes.c_char)]

class MeasConfigType(ctypes.Structure):
  _pack_ = 1
  _fields_ = [("m_StartPixel", ctypes.c_uint16),
              ("m_StopPixel", ctypes.c_uint16),
              ("m_IntegrationTime", ctypes.c_float),
              ("m_IntegrationDelay", ctypes.c_uint32),
              ("m_NrAverages", ctypes.c_uint32),
              ("m_CorDynDark_m_Enable", ctypes.c_uint8), # nesting of types does NOT work!!
              ("m_CorDynDark_m_ForgetPercentage", ctypes.c_uint8),
              ("m_Smoothing_m_SmoothPix", ctypes.c_uint16),
              ("m_Smoothing_m_SmoothModel", ctypes.c_uint8),
              ("m_SaturationDetection", ctypes.c_uint8),
              ("m_Trigger_m_Mode", ctypes.c_uint8),
              ("m_Trigger_m_Source", ctypes.c_uint8),
              ("m_Trigger_m_SourceType", ctypes.c_uint8),
              ("m_Control_m_StrobeControl", ctypes.c_uint16),
              ("m_Control_m_LaserDelay", ctypes.c_uint32),
              ("m_Control_m_LaserWidth", ctypes.c_uint32),
              ("m_Control_m_LaserWaveLength", ctypes.c_float),
              ("m_Control_m_StoreToRam", ctypes.c_uint16)]

class DeviceConfigType(ctypes.Structure):
  _pack_ = 1
  _fields_ = [("m_Len", ctypes.c_uint16),
              ("m_ConfigVersion", ctypes.c_uint16),
              ("m_aUserFriendlyId", ctypes.c_char * USER_ID_LEN),
              ("m_Detector_m_SensorType", ctypes.c_uint8),
              ("m_Detector_m_NrPixels", ctypes.c_uint16),
              ("m_Detector_m_aFit", ctypes.c_float * 5),
              ("m_Detector_m_NLEnable", ctypes.c_bool),
              ("m_Detector_m_aNLCorrect", ctypes.c_double * 8),
              ("m_Detector_m_aLowNLCounts", ctypes.c_double),
              ("m_Detector_m_aHighNLCounts", ctypes.c_double),
              ("m_Detector_m_Gain", ctypes.c_float * 2),
              ("m_Detector_m_Reserved", ctypes.c_float),
              ("m_Detector_m_Offset", ctypes.c_float * 2),
              ("m_Detector_m_ExtOffset", ctypes.c_float),
              ("m_Detector_m_DefectivePixels", ctypes.c_uint16 * 30),
              ("m_Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
              ("m_Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
              ("m_Irradiance_m_IntensityCalib_m_CalInttime", ctypes.c_float),
              ("m_Irradiance_m_IntensityCalib_m_aCalibConvers", ctypes.c_float * 4096),
              ("m_Irradiance_m_CalibrationType", ctypes.c_uint8),
              ("m_Irradiance_m_FiberDiameter", ctypes.c_uint32),
              ("m_Reflectance_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
              ("m_Reflectance_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
              ("m_Reflectance_m_CalInttime", ctypes.c_float),
              ("m_Reflectance_m_aCalibConvers", ctypes.c_float * 4096),
              ("m_SpectrumCorrect", ctypes.c_float * 4096),
              ("m_StandAlone_m_Enable", ctypes.c_bool),
              ("m_StandAlone_m_Meas_m_StartPixel", ctypes.c_uint16),
              ("m_StandAlone_m_Meas_m_StopPixel", ctypes.c_uint16),
              ("m_StandAlone_m_Meas_m_IntegrationTime", ctypes.c_float),
              ("m_StandAlone_m_Meas_m_IntegrationDelay", ctypes.c_uint32),
              ("m_StandAlone_m_Meas_m_NrAverages", ctypes.c_uint32),
              ("m_StandAlone_m_Meas_m_CorDynDark_m_Enable", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_CorDynDark_m_ForgetPercentage", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
              ("m_StandAlone_m_Meas_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_SaturationDetection", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_Trigger_m_Mode", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_Trigger_m_Source", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_Trigger_m_SourceType", ctypes.c_uint8),
              ("m_StandAlone_m_Meas_m_Control_m_StrobeControl", ctypes.c_uint16),
              ("m_StandAlone_m_Meas_m_Control_m_LaserDelay", ctypes.c_uint32),
              ("m_StandAlone_m_Meas_m_Control_m_LaserWidth", ctypes.c_uint32),
              ("m_StandAlone_m_Meas_m_Control_m_LaserWaveLength", ctypes.c_float),
              ("m_StandAlone_m_Meas_m_Control_m_StoreToRam", ctypes.c_uint16),
              ("m_StandAlone_m_Nmsr", ctypes.c_int16),
              ("m_StandAlone_m_Reserved", ctypes.c_uint8 * 12), # SD Card, do not use
              ("m_Temperature_1_m_aFit", ctypes.c_float * 5),
              ("m_Temperature_2_m_aFit", ctypes.c_float * 5),
              ("m_Temperature_3_m_aFit", ctypes.c_float * 5),
              ("m_TecControl_m_Enable", ctypes.c_bool),
              ("m_TecControl_m_Setpoint", ctypes.c_float),
              ("m_TecControl_m_aFit", ctypes.c_float * 2),
              ("m_ProcessControl_m_AnalogLow", ctypes.c_float * 2),
              ("m_ProcessControl_m_AnalogHigh", ctypes.c_float * 2),
              ("m_ProcessControl_m_DigitalLow", ctypes.c_float * 10),
              ("m_ProcessControl_m_DigitalHigh", ctypes.c_float * 10),
              ("m_EthernetSettings_m_IpAddr", ctypes.c_uint32),
              ("m_EthernetSettings_m_NetMask", ctypes.c_uint32),
              ("m_EthernetSettings_m_Gateway", ctypes.c_uint32),
              ("m_EthernetSettings_m_DhcpEnabled", ctypes.c_uint8),
              ("m_EthernetSettings_m_TcpPort", ctypes.c_uint16),
              ("m_EthernetSettings_m_LinkStatus", ctypes.c_uint8),
              ("m_Reserved", ctypes.c_uint8 * 9720),
              ("m_OemData", ctypes.c_uint8 * 4096)]

#####
# Functions
#####
def AVS_Init(x):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)
    paramflags = (1, "port",),
    AVS_Init = prototype(("AVS_Init", lib), paramflags)
    ret = AVS_Init(x)
    return ret

def AVS_UpdateUSBDevices():
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int)
    AVS_UpdateUSBDevices = prototype(("AVS_UpdateUSBDevices", lib),)
    AVS_UpdateUSBDevices.errcheck = _check_error
    ret = AVS_UpdateUSBDevices()
    return ret

def AVS_GetList(listsize, requiredsize, IDlist):
    lib = ctypes.WinDLL("avaspecx64.dll")
    # prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(AvsIdentityType))
    # paramflags = (1, "listsize",), (2, "requiredsize",), (2, "IDlist",),
    # AVS_GetList = prototype(("AVS_GetList", lib), paramflags)
    # print(listsize)
    # ret = AVS_GetList(listsize)
    # looks like you only pass the '1' parameters here
    # the '2' parameters are returned in 'ret' !!!

    return lib.AVS_GetList(
        listsize, ctypes.byref(requiredsize), ctypes.byref(IDlist)
    )

def AVS_GetNumPixels(handle, pixelsarray):
    lib = ctypes.WinDLL("avaspecx64.dll")
    # prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(AvsIdentityType))
    # paramflags = (1, "listsize",), (2, "requiredsize",), (2, "IDlist",),
    # AVS_GetList = prototype(("AVS_GetList", lib), paramflags)
    # print(listsize)
    # ret = AVS_GetList(listsize)
    # looks like you only pass the '1' parameters here
    # the '2' parameters are returned in 'ret' !!!

    lib.AVS_GetNumPixels.errcheck = _check_error

    return lib.AVS_GetNumPixels(
        handle, ctypes.byref(pixelsarray)
    )

def AVS_Activate(deviceID):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(AvsIdentityType))
    paramflags = (1, "deviceId",),
    AVS_Activate = prototype(("AVS_Activate", lib), paramflags)
    ret = AVS_Activate(deviceID)
    return ret

def AVS_UseHighResAdc(handle, enable):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool)
    paramflags = (1, "handle",), (1, "enable",),
    AVS_UseHighResAdc = prototype(("AVS_UseHighResAdc", lib), paramflags)
    ret = AVS_UseHighResAdc(handle, enable)
    return ret

def AVS_PrepareMeasure(handle, measconf):
    lib = ctypes.WinDLL("avaspecx64.dll")
    datatype = ctypes.c_byte * 41
    data = datatype()
    temp = datatype()
    temp = struct.pack("HHfIIBBHBBBBBHIIfH", measconf.m_StartPixel,
                                             measconf.m_StopPixel,
                                             measconf.m_IntegrationTime,
                                             measconf.m_IntegrationDelay,
                                             measconf.m_NrAverages,
                                             measconf.m_CorDynDark_m_Enable,
                                             measconf.m_CorDynDark_m_ForgetPercentage,
                                             measconf.m_Smoothing_m_SmoothPix,
                                             measconf.m_Smoothing_m_SmoothModel,
                                             measconf.m_SaturationDetection,
                                             measconf.m_Trigger_m_Mode,
                                             measconf.m_Trigger_m_Source,
                                             measconf.m_Trigger_m_SourceType,
                                             measconf.m_Control_m_StrobeControl,
                                             measconf.m_Control_m_LaserDelay,
                                             measconf.m_Control_m_LaserWidth,
                                             measconf.m_Control_m_LaserWaveLength,
                                             measconf.m_Control_m_StoreToRam )

# copy bytes from temp to data, otherwise you will get a typing error below
# why is this necessary?? they have the same type to start with ??
    x = 0
    while (x < 41): # 0 through 40
        data[x] = temp[x]
        x += 1
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_byte * 41)
    paramflags = (1, "handle",), (1, "measconf",),
    AVS_PrepareMeasure = prototype(("AVS_PrepareMeasure", lib), paramflags)
    AVS_PrepareMeasure.errcheck = _check_error
    ret = AVS_PrepareMeasure(handle, data)
    return ret

def AVS_Measure(handle, windowhandle, nummeas):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.wintypes.HWND, ctypes.c_uint16)
    paramflags = (1, "handle",), (1, "windowhandle",), (1, "nummeas"),
    AVS_Measure = prototype(("AVS_Measure", lib), paramflags)
    ret = AVS_Measure(handle, windowhandle, nummeas)
    return ret

class callbackclass(QObject):
    newdata = pyqtSignal()
    def __init__(self):
        QObject.__init__(self, parent)
        self.newdata.connect(PyQt5_demo.MainWindow.handle_newdata)
    def callback(self, handle, error):
        self.newdata.emit() # signal must be from a class !!

# We have not succeeded in getting the callback to execute without problem
# please use AVS_Measure instead using Windows messaging or polling

def AVS_MeasureCallback(handle, func, nummeas):
    lib = ctypes.WinDLL("avaspecx64.dll")
    # FIXED : CRASHES python
    ret = lib.AVS_MeasureCallback(handle, func, nummeas)
    return ret

def AVS_StopMeasure(handle):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)
    paramflags = (1, "handle",),
    AVS_StopMeasure = prototype(("AVS_StopMeasure", lib), paramflags)
    ret = AVS_StopMeasure(handle)
    return ret

def AVS_PollScan(handle):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int)
    paramflags = (1, "handle",),
    AVS_PollScan = prototype(("AVS_PollScan", lib), paramflags)
    ret = AVS_PollScan(handle)
    return ret

def AVS_GetScopeData(handle, timelabel, spectrum):
    lib = ctypes.WinDLL("avaspecx64.dll")

    return lib.AVS_GetScopeData(
        handle,
        ctypes.byref(timelabel),
        ctypes.byref(spectrum)
    )

def AVS_GetLambda(handle, lambdas):
    lib = ctypes.WinDLL("avaspecx64.dll")

    return lib.AVS_GetLambda(
        handle,
        ctypes.byref(lambdas)
    )

def AVS_GetParameter(handle, size, reqsize, deviceconfig):
    lib = ctypes.WinDLL("avaspecx64.dll")
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(DeviceConfigType))
    paramflags = (1, "handle",), (1, "size",), (2, "reqsize",), (2, "deviceconfig",),
    AVS_GetParameter = prototype(("AVS_GetParameter", lib), paramflags)
    ret = AVS_GetParameter(handle, size)
    return ret

def AVS_SetParameter(handle, deviceconfig):
    lib = ctypes.WinDLL("avaspecx64.dll")
    datatype = ctypes.c_byte * 63484
    data = datatype()
    temp = datatype()
    temp = struct.pack("HH64B" +
                       "BH5f?8ddd2ff2ff30H" +      # Detector
                       "HBf4096fBI" +              # Irradiance
                       "HBf4096f" +                # Reflectance
                       "4096f" +                   # SpectrumCorrect
                       "?HHfIIBBHBBBBBHIIfHH12B" + # StandAlone
                       "5f5f5f" +                  # Temperature
                       "?f2f" +                    # TecControl
                       "2f2f10f10f " +             # ProcessControl
                       "IIIBHB" +                  # EthernetSettings
                       "9720B" +                   # Reserved
                       "4096B",                    # OemData
                       deviceconfig.mLen,
                       deviceconfig.m_ConfigVersion,
                       deviceconfig.m_aUserFriendlyId,
                       deviceconfig.m_Detector_m_SensorType,
                       deviceconfig.m_Detector_m_NrPixels,
                       deviceconfig.m_Detector_m_aFit,
                       deviceconfig.m_Detector_m_NLEnable,
                       deviceconfig.m_Detector_m_aNLCorrect,
                       deviceconfig.m_Detector_m_aLowNLCounts,
                       deviceconfig.m_Detector_m_aHighNLCounts,
                       deviceconfig.m_Detector_m_Gain,
                       deviceconfig.m_Detector_m_Reserved,
                       deviceconfig.m_Detector_m_Offset,
                       deviceconfig.m_Detector_m_ExtOffset,
                       deviceconfig.m_Detector_m_DefectivePixels,
                       deviceconfig.m_Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothPix,
                       deviceconfig.m_Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothModel,
                       deviceconfig.m_Irradiance_m_IntensityCalib_m_CalInttime,
                       deviceconfig.m_Irradiance_m_IntensityCalib_m_aCalibConvers,
                       deviceconfig.m_Irradiance_m_CalibrationType,
                       deviceconfig.m_Irradiance_m_FiberDiameter,
                       deviceconfig.m_Reflectance_m_Smoothing_m_SmoothPix,
                       deviceconfig.m_Reflectance_m_Smoothing_m_SmoothModel,
                       deviceconfig.m_Reflectance_m_CalInttime,
                       deviceconfig.m_Reflectance_m_aCalibConvers,
                       deviceconfig.m_SpectrumCorrect,
                       deviceconfig.m_StandAlone_m_Enable,
                       deviceconfig.m_StandAlone_m_Meas_m_StartPixel,
                       deviceconfig.m_StandAlone_m_Meas_m_StopPixel,
                       deviceconfig.m_StandAlone_m_Meas_m_IntegrationTime,
                       deviceconfig.m_StandAlone_m_Meas_m_IntegrationDelay,
                       deviceconfig.m_StandAlone_m_Meas_m_NrAverages,
                       deviceconfig.m_StandAlone_m_Meas_m_CorDynDark_m_Enable,
                       deviceconfig.m_StandAlone_m_Meas_m_CorDynDark_m_ForgetPercentage,
                       deviceconfig.m_StandAlone_m_Meas_m_Smoothing_m_SmoothPix,
                       deviceconfig.m_StandAlone_m_Meas_m_Smoothing_m_SmoothModel,
                       deviceconfig.m_StandAlone_m_Meas_m_SaturationDetection,
                       deviceconfig.m_StandAlone_m_Meas_m_Trigger_m_Mode,
                       deviceconfig.m_StandAlone_m_Meas_m_Trigger_m_Source,
                       deviceconfig.m_StandAlone_m_Meas_m_Trigger_m_SourceType,
                       deviceconfig.m_StandAlone_m_Meas_m_Control_m_StrobeControl,
                       deviceconfig.m_StandAlone_m_Meas_m_Control_m_LaserDelay,
                       deviceconfig.m_StandAlone_m_Meas_m_Control_m_LaserWidth,
                       deviceconfig.m_StandAlone_m_Meas_m_Control_m_LaserWaveLength,
                       deviceconfig.m_StandAlone_m_Meas_m_Control_m_StoreToRam,
                       deviceconfig.m_StandAlone_m_Nmsr,
                       deviceconfig.m_StandAlone_m_Reserved,
                       deviceconfig.m_Temperature_1_m_aFit,
                       deviceconfig.m_Temperature_2_m_aFit,
                       deviceconfig.m_Temperature_3_m_aFit,
                       deviceconfig.m_TecControl_m_Enable,
                       deviceconfig.m_TecControl_m_Setpoint,
                       deviceconfig.m_TecControl_m_aFit,
                       deviceconfig.m_ProcessControl_m_AnalogLow,
                       deviceconfig.m_ProcessControl_m_AnalogHigh,
                       deviceconfig.m_ProcessControl_m_DigitalLow,
                       deviceconfig.m_ProcessControl_m_DigitalHigh,
                       deviceconfig.m_EthernetSettings_m_IpAddr,
                       deviceconfig.m_EthernetSettings_m_NetMask,
                       deviceconfig.m_EthernetSettings_m_Gateway,
                       deviceconfig.m_EthernetSettings_m_DhcpEnabled,
                       deviceconfig.m_EthernetSettings_m_TcpPort,
                       deviceconfig.m_EthernetSettings_m_LinkStatus,
                       deviceconfig.m_Reserved,
                       deviceconfig.m_OemData)
    x = 0
    while (x < 63484): # 0 through 63483
        data[x] = temp[x]
        x += 1
    prototype = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_byte * 63484)
    paramflags = (1, "handle",), (1, "deviceconfig",),
    AVS_SetParameter = prototype(("AVS_SetParameter", lib), paramflags)
    ret = AVS_SetParameter(handle, data)
    return ret

def AVS_Done():
    lib = ctypes.WinDLL("avaspecx64.dll")
    return lib.AVS_Done()
