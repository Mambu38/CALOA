#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module is basically the .dll wrapper, used to handle spectrometers.

Copyright (C) 2018  Thomas Vigouroux

This file is part of CALOA.

CALOA is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

CALOA is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with CALOA.  If not, see <http://www.gnu.org/licenses/>.
"""
import ctypes
# import os
# import enum
import logger_init
from scipy import linspace
from scipy.interpolate import CubicSpline
from scipy.signal import savgol_filter
import math
from threading import Event, Lock
from queue import Queue
import time
import avaspec

# %% CallBack Function Object for a better handling of measurments


class Callback_Measurment(Event, Queue):

    """
    Class used as a callback by AVS_MeasureCallback to notify when a
    measurment is ready.
    """

    _lock = Lock()

    @property
    def lock(self):
        return type(self)._lock

    def __init__(self):
        """
        Inits self.
        self.c_callback is the real C-like callback function.
        """
        Event.__init__(self)
        Queue.__init__(self)
        self.c_callback = \
            ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                               ctypes.POINTER(ctypes.c_int))(self.Callbackfunc)

    def Callbackfunc(self, Avh_Pointer, int_pointer):
        """
        This is the Python part of the real callback function.
        A decorator shall be used here but after some tries, it seems not to
        work.
        For further informations about this function, see AvaSpec x64-DLL
        Manual 3.3.12 AVS_MeasureCallback, callback __Done.

        Parameters :

            - Avh_Pointer -- A pointer on a AVS_Handle (integer)
            - int_pointer -- A pointer on an int
        """
        self.lock.acquire()

        # Get values pointed by pointers
        int_val = int_pointer.contents.value
        Avh_val = Avh_Pointer.contents.value
        if int_val >= 0:  # Check if any error happened.
            logger_ASH.debug("{} measurments Ready.".format(Avh_val))

            self.set()  # Set the flag to True.

            # Get the number of pixels.
            numPix = ctypes.c_short()
            logger_ASH.debug("{} : getting nr of pixels.".format(Avh_val))

            avaspec.AVS_GetNumPixels(Avh_val, numPix)

            # Prepare data structures and get pixel values.
            logger_ASH.debug("{} : getting values.".format(Avh_val))
            spect = (ctypes.c_double * numPix.value)()
            timeStamp = ctypes.c_uint()
            avaspec.AVS_GetScopeData(
                Avh_val,
                timeStamp,
                spect
            )

            # Get lambdas for all pixels.
            logger_ASH.debug("{} : getting lambdas.".format(Avh_val))
            lambdaList = (ctypes.c_double * numPix.value)()
            avaspec.AVS_GetLambda(Avh_val, lambdaList)

            logger_ASH.debug("{} : initializing spectrum instance.".format(
                Avh_val
            ))
            tp_spectrum = Spectrum(list(lambdaList), list(spect))
            self.put(tp_spectrum)

            self.lock.release()

        else:
            self.lock.release()
            raise c_AVA_Exceptions(int_val)

# %% Avantes Spectrometer Handler


logger_ASH = logger_init.logging.getLogger(__name__+".AvaSpec_Handler")


class AvaSpec_Handler:

    """
    Class used to handle AvaSpec using AvaSpec DLL, and to handle observations.
    It uses Callback_Measurment to check if a measurment is ready.
    """

    def __init__(self, mode=0):
        """
        Inits self.

        Parameters :

            - mode -- Mode to be passed to AVS_Init. For further information,
                see AvaSpec x64-DLL Manual 3.3.1 AVS_Init, parameter
                a_Port.
        """

        logger_ASH.info("Initializing AvaSpec_Handler...")

        self._nr_spec_connected = self._init(mode)
        self.devList = self._getDeviceList()
        self.lock = Lock()  # This lock is used to avoid Thread overlap.
        logger_ASH.info("AvaSpec_Handler initialized.")

    def __del__(self):
        """
        Delets self.
        """

        logger_ASH.info("Deleting AvaSpec_Handler...")

        logger_ASH.debug("Closing communications...")

        self._done()

    def _init(self, mode):
        """
        Inits avaspec and defines argtypes used by avaspec.AVS_Init as advised
        by ctypes manual.
        """

        logger_ASH.debug("Calling AVS_Init.")
        return avaspec.AVS_Init(mode)

    def _done(self):
        """
        Same as self._init.
        """

        logger_ASH.debug("Calling AVS_Done.")
        return avaspec.AVS_Done()

    def _getDeviceList(self):
        """
        Gets device list and device handler list using AVS_GetList.
        Procedure followed here is the one advised by AvaSpec x64-DLL Manual
        3.2.
        For further informations about variables, see AvaSpec x64.

        Returns :

        - dict -- key are AVS_Handles ands values are tuples as follows :
            ((str)m_aUserFriendlyId, a Callback_Measurment object)
        """
        # nrDev = avaspec.AVS_GetNrOfDevices()  # Deprecated
        nrDev = avaspec.AVS_UpdateUSBDevices()  # Newer

        if nrDev != self._nr_spec_connected:
            raise RuntimeError(
                "An unknown error happened. Number of devices changed."
            )

        ReqSize = ctypes.c_int(nrDev * ctypes.sizeof(avaspec.AvsIdentityType))
        print(ReqSize)
        AvsDevList = (avaspec.AvsIdentityType * nrDev)()

        # Get the list, further information in AvaSpec DLL manual.
        nrDev = avaspec.AVS_GetList(ReqSize,
                                    ReqSize,
                                    AvsDevList)

        # Init data types about AVS_Activate.
        avaspec.AVS_Activate.restype = ctypes.c_uint

        devDict = dict([])

        for i, dev in enumerate(AvsDevList):

            logger_ASH.debug(
                "Connecting with {}".format(dev.m_aUserFriendlyId)
            )

            # As defined above, AvsDevList is an array of c_AvsIdentityType
            # thus we initialize each AvaSpec.
            # Some tests showed that DLL may be "lazy".
            # It returns only the last part of the Id, causing it to bug later
            # when calling AVS_Activate.
            # Further tests are needed to determine if this event happens for
            # every AvaSpec or only for Double-Channel ones.

            # We patch beforehand identified problem.
            if i != 0 and len(dev.m_aSerialId) != 9:

                logger_ASH.debug(
                    "Wrong ID detected : {}".format(dev.m_aSerialId)
                )
                begin = AvsDevList[i-1].m_aSerialId[:-4]
                dev.m_aSerialId = begin + dev.m_aSerialId
                dev.m_aUserFriendlyId = begin + dev.m_aUserFriendlyId

                logger_ASH.debug(
                    "Attempted to fix it : {}".format(dev.m_aSerialId)
                )

                avs_handle = avaspec.AVS_Activate(ctypes.byref(dev))
            else:
                avs_handle = avaspec.AVS_Activate(ctypes.byref(dev))

            logger_ASH.debug(
                "Connected with {} with handle {}".format(
                    dev.m_aUserFriendlyId, avs_handle
                )
            )
            devDict[avs_handle] = \
                (bytes.decode(dev.m_aUserFriendlyId), Callback_Measurment())
            #avaspec.AVS_SetSyncMode(avs_handle, 0)
        return devDict

    def acquire(self):
        """
        Acquire self.lock
        """

        self.lock.acquire()

    def release(self):
        """
        Release self.lock
        """

        self.lock.release()

    def prepareMeasure(self, device, intTime=10, triggerred=False,
                       nrAverages=1):
        """
        Prepares a measure on device using given parameters as needed by
        AvaSpec x64-DLL Manual.

        For further information see AvaSpec x64-DLL Manual 3.3.10
        AVS_PrepareMeasure and 3.4 Data elements, MeasConfigType.

        As is, this can't be set finely, some improvements can be made.

        Parameters:
        - device -- AVS_Handle as returned by AVS_Activate corresponding to
        the device you want to use.
        - intTime -- Integration time pf the corresponding spectrometer in ms,
        experiment showed that an integration time < 1.1 causes the
        spectrometer to crash.
        - triggerred -- Boolean corresponding to wether you want the
        spectrometer to be triggered or not.
        - nrAverages -- Number of averages of the spectrometer if it is
        triggerred.
        """

        logger_ASH.debug("Preparing measurments on {}.".format(device))

        if intTime < 1.1:
            raise RuntimeError(
                "Invalid Integration time, needs to be >= 1.1 ms."
            )
        # Get the number of pixels.
        numPix = ctypes.c_short()
        avaspec.AVS_GetNumPixels(device, numPix)

        # Init c_MeasConfigType to pass it to AVS_PrepareMeasure.
        Meas = avaspec.MeasConfigType()
        Meas.m_StartPixel = ctypes.c_ushort(0)
        Meas.m_StopPixel = ctypes.c_ushort(numPix.value - 1)  # Last pixel.
        Meas.m_IntegrationTime = ctypes.c_float(intTime)
        Meas.m_IntegrationDelay = ctypes.c_uint(0)
        Meas.m_NrAverages = ctypes.c_uint(1)

        # dynamic dark correction
        Meas.m_CorDynDark_m_Enable = 0
        Meas.m_CorDynDark_m_ForgetPercentage = 100

        # Smoothig configuration
        Meas.m_Smoothing_m_SmoothPix = 1
        Meas.m_Smoothing_m_SmoothModel = 0

        # It seems that this parameter controls wether the spec is
        # hardware-triggered or not.
        # I actually don't know the reason of such an error, but it might
        # be that the dll version is not optimal.
        Meas.m_SaturationDetection = 0

        # Trigger configuration.
        Meas.m_Trigger_m_Mode = int(triggerred)
        Meas.m_Trigger_m_Source = ctypes.c_ubyte(0)
        Meas.m_Trigger_m_SourceType = ctypes.c_ubyte(0)

        # Control configuration
        Meas.m_Control_m_StrobeControl = 0
        Meas.m_Control_m_LaserDelay = 0
        Meas.m_Control_m_LaserWidth = 0
        Meas.m_Control_m_LaserWaveLength = 0.0
        Meas.m_Control_m_StoreToRam = 0

        avaspec.AVS_PrepareMeasure(device, Meas)

    def startMeasure(self, device, nmsr):
        """
        Start measure on selected device, callback is done with beforehand
        stored Callback_Measurment object.

        For further information see AvaSpec x64-DLL Manual 3.3.12

        Parameters:
        - device -- AVS_Handle as given by AVS_Activate corresponding to the
        spectrometer you want to measure with.
        - nmsr -- number of measure to be made.
        """

        calback_event = self.devList[device][1]
        calback_event.clear()
        logger_ASH.debug(
            "Starting measurment on {} current state : {}.".format(
                device,
                calback_event.wait(0)
            )
        )
        avaspec.AVS_MeasureCallback(device, calback_event.c_callback, nmsr)

    def waitMeasurmentReady(self, device):
        """
        Wait device until measurment is ready using his attached
        Callback_Measurment object.

        Parameters:
        - device -- AVS_Handle as given by AVS_Activate corresponding to the
        spectrometer you are waiting for.
        """

        while not self.devList[device][1].wait(0.1):
            pass

    def getScope(self, device):
        """
        Gather scope made by device.

        For further information see AvaSpec x64-DLL Manual 3.3.14, 3.3.17, and
        3.3.13.

        Parameters:
        - device -- AVS_Handle as given by AVS_Activate corresponding to the
        spectrometer you want to take scope from.

        Returns:
        tup -- A tuple containing the name of the spectrometer used and a
        Spectrum.
        """

        logger_ASH.debug("Gathering {} scopes.".format(device))

        id, callback = self.devList[device]

        return id, callback.get()

    def stopMeasure(self, device):
        """
        Stops the measurment on the selected device.

        For further information see AvaSpec x64-DLL Manual 3.3.27.

        Parameters:
        - device -- AVS_Handle as given by AVS_Activate
        """
        avaspec.AVS_StopMeasure(device)

    def prepareAll(self, intTime=10, triggerred=False, nrAverages=1):
        """
        Prepare all spectrometers using given parameters using
        self.prepareMeasure for all devices.

        Parameters:
        see self.prepareMeasure
        """

        for device in self.devList:
            self.prepareMeasure(
                device,
                intTime=intTime,
                triggerred=triggerred,
                nrAverages=nrAverages)

    def startAll(self, nmsr):
        """
        Starts all spectrometers using self.startMeasure

        Parameters:
        see self.startMeasure
        """

        for device in self.devList:
            self.startMeasure(device, nmsr)

    def waitAll(self):
        """
        Wait for each spectrometer to be ready to send data using
        self.waitMeasurmentReady.
        """

        for device in self.devList:
            self.waitMeasurmentReady(device)

    def getScopes(self):
        """
        Get scope for every spectrometer using self.getScope.

        Returns:
        dict -- A dict of Spectrum, with keys equals to the spectrometer name
        and values equals to the Spectrum object. this is the format expected
        by Spectrum_Storage.putSpectra.
        """

        tp_dict_to_return = dict([])
        for device in self.devList:
            tp_tup = self.getScope(device)
            tp_dict_to_return[tp_tup[0]] = tp_tup[1]
        return tp_dict_to_return

    def stopAll(self):
        """
        Stops all devices using self.stopMeasure.
        """

        for device in self.devList:
            self.stopMeasure(device)

    def getParameters(self, device):
        """
        Gets all useful informations on a device.

        For further information see AvaSpec x64-DLL 3.3.15

        Parameters:
        - device -- AVS_Handle as given by AVS_Activate corresponding to the
        device you want to have information about.

        Returns:
        Device_Config -- A c_DeviceConfigType corresponding to the divice
        config of device.
        """

        # Prepare data structures
        Device_Config = avaspec.DeviceConfigType()
        ReqSize = ctypes.c_uint(ctypes.sizeof(Device_Config))

        # Get config
        avaspec.AVS_GetParameter(
            device,
            ReqSize,
            ReqSize,
            Device_Config)

        return Device_Config

    def startAllAndGetScopes(self, nmsr=1):
        """
        Start all spectrometers and returns scopes using self.startAll,
        self.waitAll and self.getScopes.

        Parameters:
        see self.startMeasure

        Returns:
        see self.getScopes
        """
        self.startAll(nmsr)
        self.waitAll()
        return self.getScopes()

# %% Spectrum Object used for an easier handling of spectras


class Spectrum:

    """
    Useful class to store Spectrum information and to handle varied operations
    on spectra as absorbance spectrum computation.
    """

    def __init__(self, P_lambdas, P_values, P_smoothed=False):
        """
        Inits self.
        Inits a CubicSpline used as interpolation of the dataset.

        Parameters:
        - P_lambdas -- A list on values corresponding to the lambdas of the
        pixel.
        - P_values -- A list of values corresponding to the values of the
        pixel.
        - P_smoothed -- Wether the actual Spectrum is smoothed, this is meant
        to avoid to smooth multiple times.
        """

        self._lambdas = list(P_lambdas)
        self._values = list(P_values)
        self._smoothed = bool(P_smoothed)
        self._interpolator = CubicSpline(self._lambdas, self._values)

    def _get_lambdas(self):
        """
        Returns the lambdas.
        """

        return self._lambdas.copy()

    lambdas = property(_get_lambdas)

    def _get_values(self):
        """
        Returns the values.
        """

        return self._values.copy()

    values = property(_get_values)

    def __iter__(self):
        """
        Returns an iterator on self wich contains tups as follows :
            (lambda, value)
        """
        return iter(zip(self.lambdas, self.values))

    def __call__(self, P_lambda, force_computation=False):
        """
        Returns the estimated value at P_lambda

        Parameters:
        - P_lambda -- Value where you want to know the value estimation.
        """

        if (P_lambda < self.lambdas[0] or P_lambda > self.lambdas[-1])\
                and not force_computation:
                raise RuntimeError(
                    "{} is not ".format(P_lambda)
                    + "contained in spectrum range (wich is"
                    + " {} - {})".format(
                        self.lambdas[0],
                        self.lambdas[-1]
                    )
                )
        return self._interpolator(P_lambda)

    def __getstate__(self):
        """
        Returns Spectrum current state.
        """
        return self.__dict__

    def __setstate__(self, tp_dict):
        """
        Set Spectrum current state.
        """

        self.__dict__ = tp_dict

    def getInterpolated(self, startingLamb=None, endingLamb=None,
                        nrPoints=None,
                        smoothing=False, windowSize=51, polDegree=5):
        """
        Returns an interpolated version of current spectrum, mainly to save
        memory space. You can get a smoothed version of the spectrum.

        Interpolation is made using scipy.interpolate.CubicSpline, see :
        https://docs.scipy.org/doc/scipy-0.18.1/reference/generated/scipy.interpolate.CubicSpline.html

        Smoothing is made using scipy.signal.savgol_filter, see :
        https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html

        Parameters:
        - startingLamb -- Starting wavelength of interpolation. If None, this
        will be the first possible wavelength.
        - endingLamb -- Same as startingLamb but with endig wavelength.
        - nrPoints -- Number of points between startingLamb and endingLamb.
        - smoothing -- Wether you want to smooth data or not
        - windowSize -- Window size used in Savitsky-Golay filter.
        - polDegree -- polynomial degree used in Savitsky-Golay filter.

        Returns:
        a Spectrum object, corresponding to the interpolation/smoothing
        of self. This returned spectrum is set self._smoothed = True to avoid
        multiple smoothing.
        """

        # If one of startingLamb, endingLamb and nrPoints is not set, we
        # take the actual state of the dataset and will only smooth it.
        if startingLamb is None or endingLamb is None or nrPoints is None:
            startingLamb = self.lambdas[0]
            endingLamb = self.lambdas[-1]
            nrPoints = len(self.lambdas)

        # If startingLamb and endingLamb are not correctly set, we raise
        # an error.
        if startingLamb < self.lambdas[0] or endingLamb > self.lambdas[-1]\
                or startingLamb > endingLamb or polDegree >= windowSize:

            startingLamb = self.lambdas[0]
            endingLamb = self.lambdas[-1]
            nrPoints = len(self.lambdas)
            polDegree = 5
            windowSize = 51
            #raise RuntimeError(
            #    "{} - {} is not ".format(
            #        startingLamb, endingLamb
            #    )
            #    + "contained in spectrum range "
            #    + "(wich is {} - {})".format(
            #        self.lambdas[0], self.lambdas[-1]
            #    )
            #)

        if windowSize % 2 == 0:
            windowSize -= 1

        # We make a set of wavelengths equally spaced using numpy.linspace
        lamb_space = linspace(startingLamb, endingLamb, nrPoints)

        interp = None

        if smoothing:
            # As mentionned in self.__init__, we can't smooth multiple times.
            if self._smoothed:
                raise RuntimeError("This spectrum has already been smoothed.")

            # Compute the filtered dataset.
            to_interpolate = savgol_filter(self.values, windowSize, polDegree)

            # Compute the interpolation.
            interp = CubicSpline(self.lambdas, to_interpolate)
        else:
            interp = self._interpolator

        return Spectrum(lamb_space,
                        [interp(lam) for lam in lamb_space],
                        P_smoothed=True)

    def isSaturated(self):
        """
        Check if some pixels are saturated.
        """
        return max(self.values) >= avaspec.AVS_SATURATION_VALUE - 1

    def absorbanceSpectrum(reference, spectrum):
        """
        Returns the absorbance spectrum using reference and spectrum.

        For further informations about absorbance formulas, see:
            http://en.wikipedia.org/wiki/Absorbance

        Warning:
        If any value is impossible to compute, default value will be 0.

        Parameters:
        - reference -- Reference spectrum to compute absorbance.
        - spectrum -- Spectrum containing absorbance.

        Returns:
        a Spectrum object, wich has wavelengths as lambdas, and absorbance as
        values.
        """

        opacity_spectrum = reference/spectrum

        l_lambdas = opacity_spectrum.lambdas
        l_values = [math.log10(val) if val > 0 else 0
                    for val in opacity_spectrum.values]

        return Spectrum(l_lambdas, l_values)

    # Following methods are used to handle spectrum operations.
    # Computations are made as follows :
    # - get the smallest set of lambdas (in term of information)
    # - compute using Spectrum.__call__ the appropriate operation
    # - return the computed Spectrum
    # If one of the spectra is smoothed, result will be marked as smoothed.

    def __add__(self, spectrum):
        """
        Adds self and spectrum.
        """

        smoothed = self._smoothed or spectrum._smoothed

        l_lambdas = self.lambdas if len(self.lambdas) > len(spectrum.lambdas)\
            else spectrum.lambdas

        l_values = [
            self(lam, force_computation=True)
            + spectrum(lam, force_computation=True)
            for lam in l_lambdas
        ]

        return Spectrum(l_lambdas, l_values, P_smoothed=smoothed)

    def __sub__(self, spectrum):
        """
        Substract self and spectrum.
        """

        smoothed = self._smoothed or spectrum._smoothed

        l_lambdas = self.lambdas if len(self.lambdas) > len(spectrum.lambdas)\
            else spectrum.lambdas

        l_values = [
            self(lam, force_computation=True)
            - spectrum(lam, force_computation=True)
            for lam in l_lambdas
        ]

        return Spectrum(l_lambdas, l_values, P_smoothed=smoothed)

    def __truediv__(self, spectrum):
        """
        Divides self and spectrum.
        """
        if isinstance(spectrum, (int, float)) and spectrum != 0:
            return Spectrum(
                self.lambdas,
                [actual/spectrum for actual in self.values]
            )

        smoothed = self._smoothed or spectrum._smoothed

        l_lambdas = self.lambdas if len(self.lambdas) > len(spectrum.lambdas)\
            else spectrum.lambdas

        l_values = [
            self(lam, force_computation=True)
            / spectrum(lam, force_computation=True)
            if spectrum(lam) > 0 else 0
            for lam in l_lambdas
        ]

        return Spectrum(l_lambdas, l_values, P_smoothed=smoothed)

    def __mul__(self, spectrum):
        """
        Multiply self and spectrum.
        """

        smoothed = self._smoothed or spectrum._smoothed

        l_lambdas = self.lambdas if len(self.lambdas) > len(spectrum.lambdas)\
            else spectrum.lambdas

        l_values = [
            self(lam, force_computation=True)
            * spectrum(lam, force_computation=True)
            for lam in l_lambdas
        ]

        return Spectrum(l_lambdas, l_values, P_smoothed=smoothed)

    def __imul__(self, spectrum):
        """
        Incremental version of self.__mul__
        """

        return self * spectrum

    def __iadd__(self, spectrum):
        """
        Incremental version of self.__add__
        """

        return self + spectrum

    def __itruediv__(self, spectrum):
        """
        Incremental version on self.__truediv__
        """

        return self/spectrum
# %% Spectrum_Storage class, useful for further improvements on
# spectrum handling


class Spectrum_Storage:

    """
    This class is meant to be used as a storage for spectra.
    It may be useful for further improvements of application.
    It will store all desired spectra in a folder-like way.

    Some basic "folders" are pre-built for a better handling.

    "folder" arborescence is as follows :

    Spectrum_Storage
    |- Basic
    |  |- Black
    |  |  |- [CHAN ID] : Spectrum
    |  |  |- [OTHER CHAN ID] : Spectrum
    |  |  :
    |  |- White
    |  |  :
    |- [TIMESTAMP]
    |  |- 1
    |  |  |- [CHAN ID] : Spectrum ...
    |  |  :
    |  |- 2
    |  |  :
    |  :
    |- [OTHER TIMESTAMP]
    |  :
    :
    """

    def get_timestamp(self, end=""):
        """Creates the time current time stamp as follows :
        DD:MM:YYYY_HH:MM:SS
        Where in the same order :
            D = a day number digit
            M = a month number digit
            Y = a year number digit
            H = an hour number digit
            M = a minute number digit
            S = a second number digit
        """
        tp_time_stamp = \
            "{time.tm_mday}-{time.tm_mon}-{time.tm_year}_{time.tm_hour}-{time.tm_min}-{time.tm_sec}".\
            format(time=time.localtime())

        if end != "":
            tp_time_stamp += "_{}".format(end)
        return tp_time_stamp

    def createStorageUnit(self, end=""):
        """
        Inits a storage unit in the storage space, time_stamp itm and returns
        his identifier (timestamp).
        """
        cur_timestamp = self.get_timestamp(end=end)
        self._hidden_directory[cur_timestamp] = dict([])
        return cur_timestamp

    def __init__(self):
        """Inits self and creates basic storage space."""
        self._hidden_directory = {"Basic": dict([])}

    def __getitem__(self, indicator_tuple):
        """
        Get a spectrum or a list of spectra depending on
        the given indicator_tuple.
        The first index of indicator_tuple must be a Spectrum-folder identifier
            (a timestamp given by createStorageUnit method) or a slice of
            Spectrum-folder identifiers wich don't includes "Basic"
        The second can be an integer or slice of integers.
        The third and last must be an integer or slice of integers.
        """

        if len(indicator_tuple) != 3:
            raise ValueError("Argument don't have correct length.")

        class_types = tuple(map(type, indicator_tuple))

        if class_types[0] not in (str, slice):
            raise ValueError("Argument nr 1 is not of the correct type."
                             + " Expected one of : str, slice."
                             + " Found {}.".format(class_types[0]))

        if class_types[1] not in (int, slice):
            raise ValueError("Argument nr 2 is not of the correct type."
                             + " Expected one of : int, slice."
                             + " Found {}.".format(class_types[0]))

        if class_types[2] not in (str, slice):
            raise ValueError("Argument nr 3 is not of the correct type."
                             + " Expected one of : str, slice."
                             + " Found {}.".format(class_types[0]))

        for i in range(3):
            if class_types[i] == slice:
                if indicator_tuple[i] != slice(None, None, None):
                    raise ValueError("Use slices only with \":\"")

        if class_types == (str, int, str):

            # Her the user wants to see only one spectrum

            choosen_folder = self._hidden_directory[indicator_tuple[0]]
            choosen_subfolder = choosen_folder[indicator_tuple[1]]
            return choosen_subfolder[indicator_tuple[2]]

        elif class_types == (slice, int, str):

            # In this case the user wants to see all spectra corresponding
            # to one delay and one spectrometer.

            tp_dict_to_return = dict([])

            for key in self._hidden_directory.keys():
                if key != "Basic":
                    tp_dict_to_return[key] =\
                        self._hidden_directory[key][
                        indicator_tuple[1]][
                        indicator_tuple[2]]
            return tp_dict_to_return

        elif class_types == (str, slice, str):

            # Here we need to return a dict containing all spectra that come
            # from the same spectrometer and from the same folder

            tp_dict_to_return = dict([])

            folder = self._hidden_directory[indicator_tuple[0]]
            for key in folder.keys():
                tp_dict_to_return[key] = folder[key][indicator_tuple[2]]

            return tp_dict_to_return

        elif class_types == (str, int, slice):

            # Here we want all spectra corresponding to one delay and from
            # the same folder

            return self._hidden_directory[indicator_tuple[0]][
                indicator_tuple[1]]

        elif class_types == (slice, slice, str):

            # This corresponds to all spectra coming from the same spectrometer

            tp_dict_to_return = dict([])

            for folder_id in self._hidden_directory.keys():
                tp_dict_to_append = dict([])

                for subfolder_id in self._hidden_directory[folder_id].keys():
                    tp_dict_to_append[subfolder_id] =\
                        self._hidden_directory[folder_id][subfolder_id][
                        indicator_tuple[2]]

            return tp_dict_to_return

        elif class_types == (slice, int, slice):

            # This is all spectra with the same delay number (subfolder_id)

            tp_dict_to_return = dict([])

            for folder_id in self._hidden_directory.keys():
                tp_dict_to_return[folder_id] =\
                    self._hidden_directory[folder_id][indicator_tuple[1]]

            return tp_dict_to_return

        elif class_types == (str, slice, slice):

            # This is all spectra in the same folder

            return self._hidden_directory[indicator_tuple[0]]

        else:
            return self._hidden_directory

    def putSpectra(self, folder_id, subfolder_id, spectra):
        """
        Put given spectra in the selected folder.
        First we create a new subfolder (append it in the folder)
        Then we create a subfolder.
        Then we associate channel id to the corresponding Spectrum.
        We base this method on AvaSpec_Handler.getScopes, which returns a dict:

            {channel_id: spectrum, ...}
        """

        if folder_id not in self._hidden_directory:
            raise IndexError(
                "{} is not a correct folder id.".format(folder_id)
            )
        if subfolder_id in self._hidden_directory[folder_id] \
                and folder_id != "Basic":
            raise IndexError(
                "{} is already in folder {}.".format(subfolder_id, folder_id)
            )

        if not isinstance(subfolder_id, int) and folder_id != "Basic":
            raise TypeError(
                "subfolder_id must be an integer."
            )

        self._hidden_directory[folder_id][subfolder_id] = spectra

    def putBlack(self, new_spectra):

        self._hidden_directory["Basic"]["Black"] = new_spectra

    def getBlack(self):

        return self._hidden_directory["Basic"]["Black"]

    latest_black = property(getBlack, putBlack)

    def putWhite(self, new_spectra):

        self._hidden_directory["Basic"]["White"] = new_spectra

    def getWhite(self):

        return self._hidden_directory["Basic"]["White"]

    latest_white = property(getWhite, putWhite)

    def blackIsSet(self):

        return "Black" in self._hidden_directory["Basic"]

    def whiteIsSet(self):

        return "White" in self._hidden_directory["Basic"]

    def isExperimentReady(self):

        return self.blackIsSet() and self.whiteIsSet()

    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, saved):
        self.__dict__ = saved
