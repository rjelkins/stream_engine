import base64
import json
import os
import unittest
import uuid
from cassandra.cluster import Cluster
from cassandra.protocol import ConfigurationException
import msgpack
import numpy
from engine import app
from model.preload import Parameter, Stream
from util.calc import DataParameter, FunctionParameter, StreamRequest, CalibrationParameter, msgpack_one, interpolate, \
    build_func_map, execute_one_dpa, execute_dpas, calculate
from util.cass import fetch_data, global_cassandra_state
from util.preload_insert import create_db

import sys

sys.path.append('../ion-functions')

from ion_functions.data import ctd_functions, sfl_functions

METADATA_TABLE = \
    '''CREATE TABLE stream_metadata (
  subsite text,
  node text,
  sensor text,
  method text,
  stream text,
  count bigint,
  first double,
  last double,
  PRIMARY KEY ((subsite, node, sensor), method, stream))'''

CTDBP_NO_SAMPLE_TABLE = \
    '''CREATE TABLE ctdbp_no_sample (
  subsite text,
  node text,
  sensor text,
  method text,
  time double,
  id uuid,
  conductivity int,
  driver_timestamp double,
  ingestion_timestamp double,
  internal_timestamp double,
  oxy_calphase int,
  oxy_temp int,
  oxygen int,
  port_timestamp double,
  preferred_timestamp text,
  pressure int,
  pressure_temp int,
  provenance int,
  quality_flag text,
  temperature int,
  PRIMARY KEY ((subsite, node, sensor), method, time, id))'''

CTDBP_NO_CALIBRATION_COEFFICIENTS_TABLE = \
    '''CREATE TABLE ctdbp_no_calibration_coefficients (
  subsite text,
  node text,
  sensor text,
  method text,
  time double,
  id uuid,
  calibration_date_conductivity text,
  calibration_date_pressure text,
  calibration_date_temperature text,
  cond_coeff_cg double,
  cond_coeff_ch double,
  cond_coeff_ci double,
  cond_coeff_cj double,
  cond_coeff_cpcor double,
  cond_coeff_cslope double,
  cond_coeff_ctcor double,
  cond_sensor_serial_number int,
  driver_timestamp double,
  ext_freq_sf double,
  ext_volt0_offset double,
  ext_volt0_slope double,
  ext_volt1_offset double,
  ext_volt1_slope double,
  ext_volt2_offset double,
  ext_volt2_slope double,
  ext_volt3_offset double,
  ext_volt3_slope double,
  ext_volt4_offset double,
  ext_volt4_slope double,
  ext_volt5_offset double,
  ext_volt5_slope double,
  ingestion_timestamp double,
  internal_timestamp double,
  port_timestamp double,
  preferred_timestamp text,
  press_coeff_pc1 double,
  press_coeff_pc2 double,
  press_coeff_pc3 double,
  press_coeff_pd1 double,
  press_coeff_pd2 double,
  press_coeff_poffset double,
  press_coeff_pslope double,
  press_coeff_pt1 double,
  press_coeff_pt2 double,
  press_coeff_pt3 double,
  press_coeff_pt4 double,
  press_serial_number int,
  pressure_sensor_range int,
  provenance int,
  quality_flag text,
  serial_number int,
  temp_coeff_offset double,
  temp_coeff_ta0 double,
  temp_coeff_ta1 double,
  temp_coeff_ta2 double,
  temp_coeff_ta3 double,
  temp_sensor_serial_number int,
  PRIMARY KEY ((subsite, node, sensor), method, time, id)
)'''


class StreamUnitTestMixin(object):
    subsite = 'SUBSITE'
    node = 'NODE'
    sensor = 'SENSOR'
    method = 'METHOD'
    stream = 'STREAM'

    @classmethod
    def get_ctdbp_no_data(cls):
        return {
            'subsite': cls.subsite,
            'node': cls.node,
            'sensor': cls.sensor,
            'method': cls.method,
            'time': 1,
            'id': None,
            'conductivity': 1396258,
            'driver_timestamp': 1,
            'ingestion_timestamp': 1,
            'internal_timestamp': 1,
            'oxy_calphase': 34407,
            'oxy_temp': 23002,
            'oxygen': 1724210,
            'port_timestamp': 1,
            'preferred_timestamp': "port_timestamp",
            'pressure': 8597725,
            'pressure_temp': 28282,
            'provenance': 0,
            'quality_flag': "ok",
            'temperature': 418687,
        }

    @classmethod
    def get_ctdbp_no_calibration_coefficients_data(cls):
        return {
            'calibration_date_conductivity': u'07-Dec-13',
            'calibration_date_pressure': u'05-Dec-13',
            'calibration_date_temperature': u'07-Dec-13',
            'cond_coeff_cg': -0.9788709,
            'cond_coeff_ch': 0.1512588,
            'cond_coeff_ci': -0.0003713968,
            'cond_coeff_cj': 5.045781e-05,
            'cond_coeff_cpcor': -9.57e-08,
            'cond_coeff_cslope': 1.0,
            'cond_coeff_ctcor': 3.25e-06,
            'cond_sensor_serial_number': 1907248,
            'driver_timestamp': 1,
            'ext_freq_sf': 0.9999914,
            'ext_volt0_offset': -0.04811895,
            'ext_volt0_slope': 1.249131,
            'ext_volt1_offset': -0.04744,
            'ext_volt1_slope': 1.24839,
            'ext_volt2_offset': -0.04766632,
            'ext_volt2_slope': 1.248002,
            'ext_volt3_offset': -0.04679579,
            'ext_volt3_slope': 1.248234,
            'ext_volt4_offset': -0.04870526,
            'ext_volt4_slope': 1.248589,
            'ext_volt5_offset': -0.04749474,
            'ext_volt5_slope': 1.24836,
            'id': 0,
            'ingestion_timestamp': 1,
            'internal_timestamp': 1,
            'method': cls.method,
            'node': cls.node,
            'port_timestamp': 1,
            'preferred_timestamp': u'port_timestamp',
            'press_coeff_pc1': 999.0941,
            'press_coeff_pc2': -0.00556102,
            'press_coeff_pc3': -0.000130274,
            'press_coeff_pd1': 0.03038,
            'press_coeff_pd2': 0.0,
            'press_coeff_poffset': 0.0,
            'press_coeff_pslope': 1.0,
            'press_coeff_pt1': 27.70606,
            'press_coeff_pt2': -0.000104193,
            'press_coeff_pt3': 1.06286e-06,
            'press_coeff_pt4': 1.56172e-09,
            'press_serial_number': 125046,
            'pressure_sensor_range': 200,
            'provenance': 0,
            'quality_flag': u'ok',
            'sensor': cls.sensor,
            'serial_number': 1907248,
            'subsite': cls.subsite,
            'temp_coeff_offset': 0.0,
            'temp_coeff_ta0': 0.001268802,
            'temp_coeff_ta1': 0.0002709596,
            'temp_coeff_ta2': -8.126484e-07,
            'temp_coeff_ta3': 1.699432e-07,
            'temp_sensor_serial_number': 1907248,
            'time': 1
        }

    def get_ctdpf_ckl_items(self):
        stream = Stream.query.filter(Stream.name == 'ctdpf_ckl_wfp_instrument_recovered').first()
        parameters = stream.parameters
        temperature = DataParameter(self.subsite, self.node, self.sensor,
                                    self.stream, self.method, Parameter.query.get(193))
        conductivity = DataParameter(self.subsite, self.node, self.sensor,
                                     self.stream, self.method, Parameter.query.get(194))
        pressure = DataParameter(self.subsite, self.node, self.sensor,
                                 self.stream, self.method, Parameter.query.get(195))
        ctdpf_ckl_seawater_pressure = FunctionParameter(self.subsite, self.node, self.sensor,
                                                        self.stream, self.method, Parameter.query.get(1959))
        ctdpf_ckl_seawater_temperature = FunctionParameter(self.subsite, self.node, self.sensor,
                                                           self.stream, self.method, Parameter.query.get(1960))
        ctdpf_ckl_seawater_conductivity = FunctionParameter(self.subsite, self.node, self.sensor,
                                                            self.stream, self.method, Parameter.query.get(1961))
        ctdpf_ckl_sci_water_pracsal = FunctionParameter(self.subsite, self.node, self.sensor,
                                                        self.stream, self.method, Parameter.query.get(1962))
        ctdpf_ckl_seawater_density = FunctionParameter(self.subsite, self.node, self.sensor,
                                                       self.stream, self.method, Parameter.query.get(1963))

        times = [1.0, 2.0, 3.0]
        temperature.data = numpy.array([254779, 254779, 254779])
        conductivity.data = numpy.array([6792, 6792, 6792])
        pressure.data = numpy.array([1003, 1003, 1003])
        temperature.times = times
        conductivity.times = times
        pressure.times = times

        stream_request = StreamRequest(self.subsite, self.node, self.sensor, self.method, stream, parameters, {})
        stream_request.data = [temperature, conductivity, pressure]
        stream_request.functions = [ctdpf_ckl_seawater_pressure, ctdpf_ckl_seawater_temperature,
                                    ctdpf_ckl_seawater_conductivity, ctdpf_ckl_sci_water_pracsal,
                                    ctdpf_ckl_seawater_density]

        coefficients = {'CC_latitude': 1.0, 'CC_longitude': 1.0}

        for name in coefficients:
            stream_request.coeffs.append(CalibrationParameter(self.subsite, self.node, self.sensor,
                                                              name, coefficients[name]))

        return stream_request, coefficients

    def create_stream_request(self, stream_name):
        stream = Stream.query.filter(Stream.name == stream_name).first()
        parameters = stream.parameters
        stream_request = StreamRequest(self.subsite, self.node, self.sensor, self.method, stream, parameters, {})
        for parameter in parameters:
            stream_request.add_parameter(parameter, self.subsite, self.node, self.sensor, stream_name, self.method)

        return stream_request

    def get_thsph_sample_data(self):
        # TODO: these values produce output out of range, get better data
        # 2260,       2261,        2262,      2263,      2264,        2265,        2266,        2267
        # counts_ysz, counts_agcl, counts_h2, counts_hs, tc_rawdec_H, tc_rawdec_L, ts_rawdec_r, ts_rawdec_b
        return numpy.array([
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
            [7807.0, 7801.0, 4907.0, 3806.0, 9237.0, 16012.0, 8770.0, 8188.0],
        ])

    def get_thsph_stream_request(self):
        stream_request = self.create_stream_request('thsph_sample')
        data_map = stream_request.get_data_map()

        test_array = self.get_thsph_sample_data()

        data_map.get(2260).data = test_array[:, 0]
        data_map.get(2261).data = test_array[:, 1]
        data_map.get(2262).data = test_array[:, 2]
        data_map.get(2263).data = test_array[:, 3]
        data_map.get(2264).data = test_array[:, 4]
        data_map.get(2265).data = test_array[:, 5]
        data_map.get(2266).data = test_array[:, 6]
        data_map.get(2267).data = test_array[:, 7]

        for each in data_map.itervalues():
            if each.data is not None:
                each.times = numpy.arange(1.0, 1.0 + len(each.data))

        coefficients = {
            'CC_e2l_H': [0.0, 0.0, 0.0, 0.0, 0.9979, -0.10287],
            'CC_e2l_hs': [0.0, 0.0, 0.0, 0.0, 1.0, -0.00375],
            'CC_e2l_h2': [0.0, 0.0, 0.0, 0.0, 1.0, -0.00350],
            'CC_l2s_H': [9.32483e-7, -0.000122268, 0.00702, -0.23532, 17.06172, 0.0],
            'CC_l2s_r': [0.0, 0.0, 8.7755e-08, 0.0, 0.000234101, 0.001129306],
            'CC_s2v_r': [5.83124e-14, -4.09038e-11, -3.44498e-8, 5.14528e-5, 0.05841, 0.00209],
            'CC_e2l_r': [0.0, 0.0, 0.0, 0.0, 1.04938, -275.5],
            'CC_e2l_L': [0.0, 0.0, 0.0, 0.0, 0.9964, -0.46112],
            'CC_e2l_b': [0.0, 0.0, 0.0, 0.0, 1.04938, -275.5],
            'CC_e2l_agcl': [0.0, 0.0, 0.0, 0.0, 1.0, -0.00225],
            'CC_arr_agclref': [0.0, 0.0, -2.5E-10, -2.5E-08, -2.5E-06, -9.025E-02],
            'CC_l2s_L': [9.32483e-7, -0.000122268, 0.00702, -0.23532, 17.06172, 0.0],
            'CC_l2s_b': [0.0, 0.0, 8.7755e-08, 0.0, 0.000234101, 0.001129306],
            'CC_e2l_ysz': [0.0, 0.0, 0.0, 0.0, 1.0, -0.00375],
            'CC_arr_agcl': [0.0, -8.61134E-10, 9.21187E-07, -3.7455E-04, 6.6550E-02, -4.30086],
            'CC_arr_hgo': [0.0, 0.0, 4.38978E-10, -1.88519E-07, -1.88232E-04, 9.23720E-01],
            'CC_arr_tac': [0.0, 0.0, -2.80979E-09, 2.21477E-06, -5.53586E-04, 5.723E-02],
            'CC_arr_tbc1': [0.0, 0.0, -6.59572E-08, 4.52831E-05, -1.204E-02, 1.70059],
            'CC_arr_tbc2': [0.0, 0.0, 8.49102E-08, -6.20293E-05, 1.485E-02, -1.41503],
            'CC_arr_tbc3': [-1.86747E-12, 2.32877E-09, -1.18318E-06, 3.04753E-04, -3.956E-02, 2.2047],
            'CC_arr_eh2sg': [0.0, 0.0, 0.0, 0.0, -4.49477E-05, -1.228E-02],
            'CC_arr_yh2sg': [2.3113E+01, -1.8780E+02, 5.9793E+02, -9.1512E+02, 6.7717E+02, -1.8638E+02],
            'CC_arr_logkfh2g': [0.0, 0.0, -1.51904000E-07, 1.16655E-04, -3.435E-02, 6.32102],
        }

        for name in coefficients:
            stream_request.coeffs.append(CalibrationParameter(self.subsite, self.node, self.sensor,
                                                              name, coefficients[name]))

        return stream_request, coefficients

    def get_trhph_sample_data(self):
        # TODO: these values produce output out of range, get better data
        # V_ts, V_tc, T_ts, T, V, ORP, v_r1, v_r2, v_r3
        return numpy.array([
            # [1.930,	1.000,	2.38, 12.0, 1.806, -50., 0.440, 4.095, 4.095],
            # [1.926,	1.288,	2.47, 17.1, 1.541, -116., 0.320, 4.095, 4.095],
            [1.926, 1.305, 2.47, 2.1, 1.810, -48., 0.184, 0.915, 4.064],
            [1.926, 1.305, 2.47, 2.1, 1.810, -48., 0.184, 0.915, 4.064],
            [1.926, 1.305, 2.47, 2.1, 1.810, -48., 0.184, 0.915, 4.064],
            [1.928, 1.319, 2.43, 69.5, 0.735, -317., 0.198, 1.002, 4.095],
            [1.929, 1.318, 2.40, 77.5, 0.745, -315., 0.172, 0.857, 4.082],
        ])

    def get_trhph_stream_request(self):
        stream_request = self.create_stream_request('trhph_sample')
        data_map = stream_request.get_data_map()

        test_array = self.get_trhph_sample_data()

        data_map.get(428).data = test_array[:, 0]
        data_map.get(430).data = test_array[:, 1]
        data_map.get(427).data = test_array[:, 4]
        data_map.get(421).data = test_array[:, 6]
        data_map.get(422).data = test_array[:, 7]
        data_map.get(423).data = test_array[:, 8]

        for each in data_map.itervalues():
            if each.data is not None:
                each.times = numpy.arange(1.0, 1.0 + len(each.data) * 1.5, 1.5)

        coefficients = {'CC_ts_slope': 0.003,
                        'CC_tc_slope': 4.22e-5,
                        'CC_gain': 4.0,
                        'CC_offset': 2004.0}

        for name in coefficients:
            stream_request.coeffs.append(CalibrationParameter(self.subsite, self.node, self.sensor,
                                                              name, coefficients[name]))
        return stream_request, coefficients


class StreamUnitTest(unittest.TestCase, StreamUnitTestMixin):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(app.config['DBFILE_LOCATION']):
            create_db()

        app.config['CASSANDRA_KEYSPACE'] = 'stream_engine_test'
        cluster = Cluster(app.config['CASSANDRA_CONTACT_POINTS'],
                          control_connection_timeout=app.config['CASSANDRA_CONNECT_TIMEOUT'])
        global_cassandra_state['cluster'] = cluster
        session = cluster.connect()
        try:
            session.execute('drop keyspace %s' % app.config['CASSANDRA_KEYSPACE'])
        except ConfigurationException:
            pass
        session.execute("create keyspace %s with replication = { 'class' : 'SimpleStrategy', 'replication_factor' : 1}"
                        % app.config['CASSANDRA_KEYSPACE'])

        session.set_keyspace(app.config['CASSANDRA_KEYSPACE'])
        session.execute(METADATA_TABLE)
        session.execute(CTDBP_NO_SAMPLE_TABLE)
        session.execute(CTDBP_NO_CALIBRATION_COEFFICIENTS_TABLE)

        d = cls.get_ctdbp_no_data()
        for x in range(1, 10):
            d['time'] = float(x)
            d['id'] = uuid.uuid4()
            keys = sorted(d.keys())
            values = [d[k] for k in keys]
            stmt = 'insert into ctdbp_no_sample (%s) values (%s)' % (','.join(keys), ','.join(['%s' for _ in keys]))
            session.execute(stmt, values)

        d = cls.get_ctdbp_no_calibration_coefficients_data()
        d['id'] = uuid.uuid4()
        keys = sorted(d.keys())
        values = [d[k] for k in keys]
        stmt = 'insert into ctdbp_no_calibration_coefficients (%s) values (%s)' % (','.join(keys), ','.join(['%s' for _ in keys]))
        session.execute(stmt, values)

        session.execute('insert into stream_metadata (subsite, node, sensor, method, stream, count, first, last) values (%s, %s, %s, %s, %s, %s, %s, %s)',
                        (cls.subsite, cls.node, cls.sensor, cls.method, 'ctdbp_no_calibration_coefficients', 1, 1, 1))

    def test_parameters(self):
        """
        Test whether we can retrieve a parameter by id and verify that
        it contains the correct data.
        :return:
        """
        pmap = {
            195: {
                'name': 'pressure',
                'ptype': 'quantity',
                'encoding': 'int32',
                'needs': [195],
                'cc': [],
            },
            1963: {
                'name': 'ctdpf_ckl_seawater_density',
                'ptype': 'function',
                'encoding': 'float32',
                'needs': [193, 194, 195, 1959, 1960, 1961, 1962, 1963],
                'cc': ['CC_latitude', 'CC_longitude'],
            },
        }

        # by id
        for pdid in pmap:
            parameter = Parameter.query.get(pdid)
            self.assertIsNotNone(parameter)
            self.assertEqual(parameter.name, pmap[pdid]['name'])
            self.assertEqual(parameter.id, pdid)
            self.assertEqual(parameter.parameter_type.value, pmap[pdid]['ptype'])
            self.assertEqual(parameter.value_encoding.value, pmap[pdid]['encoding'])
            self.assertEqual(sorted([p.id for p in parameter.needs()]), pmap[pdid]['needs'])
            self.assertEqual(sorted(parameter.needs_cc()), pmap[pdid]['cc'])

            # by name (FAILS, parameter names are not unique!)
            # for pdid in pmap:
            # parameter = Parameter.query.filter(Parameter.name == pmap[pdid]['name']).first()
            # self.assertIsNotNone(parameter)
            # self.assertEqual(parameter.name, pmap[pdid]['name'])
            # self.assertEqual(parameter.id, pdid)
            # self.assertEqual(parameter.parameter_type.value, pmap[pdid]['ptype'])
            #     self.assertEqual(parameter.value_encoding.value, pmap[pdid]['encoding'])
            #     self.assertEqual(sorted([p.id for p in parameter.needs()]), pmap[pdid]['needs'])
            #     self.assertEqual(sorted(parameter.needs_cc()), pmap[pdid]['cc'])

    def test_streams(self):
        """
        Test if we can retrieve a stream by name and verify that it contains
        the correct parameters.
        :return:
        """
        stream = Stream.query.filter(Stream.name == 'thsph_sample').first()
        self.assertEqual(stream.name, 'thsph_sample')
        self.assertEqual([p.id for p in stream.parameters],
                         [7, 10, 11, 12, 863, 2260, 2261, 2262, 2263,
                          2264, 2265, 2266, 2267, 2624, 2625, 2626,
                          2627, 2628, 2629, 2630, 2631, 2632, 2633, 2634, 2635])

    def test_msgpack(self):
        """
        Create a DataParameter, msgpack it, then verify we can retrieve the
        original message contents.
        :return:
        """
        parameter = Parameter.query.get(193)
        p = DataParameter(self.subsite, self.node, self.sensor, self.stream, self.method, parameter)
        p.data = numpy.array([[1, 2, 3], [4, 5, 6]])
        p.shape = p.data.shape
        p.dtype = p.data.dtype

        packed = msgpack_one(p)
        unpacked = msgpack.unpackb(base64.b64decode(packed['data']))
        self.assertTrue(numpy.array_equal(p.data, numpy.array(unpacked).reshape(p.shape)))

    def test_build_func_map(self):
        """
        Create a DataParameter and FunctionParameter and verify the correct set of arguments
        is generated.
        :return:
        """
        stream_request, coefficients = self.get_ctdpf_ckl_items()
        interpolate(stream_request)
        data_map = stream_request.get_data_map()

        dp = data_map.get(195)
        fp = data_map.get(1959)

        dp.data = numpy.array([1, 2, 3])
        kwargs = build_func_map(fp, {195: dp})
        expected_kwargs = {'p0': dp.data}

        self.assertEqual(expected_kwargs, kwargs)

    def test_execute_one_dpa(self):
        """
        Create a DataParameter and FunctionParameter and verify the DPA output matches a direct call to the
        corresponding method from ion_functions.
        :return:
        """
        stream_request, coefficients = self.get_ctdpf_ckl_items()
        interpolate(stream_request)
        data_map = stream_request.get_data_map()

        dp = data_map.get(195)
        fp = data_map.get(1959)

        dp.data = numpy.array([1, 2, 3])
        kwargs = build_func_map(fp, {195: dp})
        execute_one_dpa(fp, kwargs)

        self.assertTrue(numpy.array_equal(fp.data, ctd_functions.ctd_sbe52mp_preswat(dp.data)))

    def test_execute_dpas(self):
        """
        Execute multiple dependent DPAs on a single stream, compare output to directly computed results.
        :return:
        """
        # ctdpf_ckl
        stream_request, coefficients = self.get_ctdpf_ckl_items()
        data_map = stream_request.get_data_map()
        interpolate(stream_request)
        execute_dpas(stream_request)

        expected_pressure = ctd_functions.ctd_sbe52mp_preswat(data_map.get(195).data)
        expected_temperature = ctd_functions.ctd_sbe52mp_tempwat(data_map.get(193).data)
        expected_conductivity = ctd_functions.ctd_sbe52mp_condwat(data_map.get(194).data)
        expected_pracsal = ctd_functions.ctd_pracsal(expected_conductivity, expected_temperature, expected_pressure)
        expected_density = ctd_functions.ctd_density(expected_pracsal, expected_temperature, expected_pressure,
                                                     coefficients['CC_latitude'], coefficients['CC_longitude'])

        self.assertTrue(numpy.array_equal(data_map.get(1959).data, expected_pressure))
        self.assertTrue(numpy.array_equal(data_map.get(1960).data, expected_temperature))
        self.assertTrue(numpy.array_equal(data_map.get(1961).data, expected_conductivity))
        self.assertTrue(numpy.array_equal(data_map.get(1962).data, expected_pracsal))
        self.assertTrue(numpy.array_equal(data_map.get(1963).data, expected_density))

        # trhph
        stream_request, coefficients = self.get_trhph_stream_request()
        interpolate(stream_request)
        data_map = stream_request.get_data_map()
        execute_dpas(stream_request)
        expected_vfltemp = sfl_functions.sfl_trhph_vfltemp(data_map.get(428).data, data_map.get(430).data,
                                                           data_map.get('CC_tc_slope').value,
                                                           data_map.get('CC_ts_slope').value)
        expected_vflchlor = sfl_functions.sfl_trhph_chloride(data_map.get(421).data, data_map.get(422).data,
                                                             data_map.get(423).data, expected_vfltemp)
        expected_vflorp = sfl_functions.sfl_trhph_vflorp(data_map.get(427).data, data_map.get('CC_offset').value,
                                                         data_map.get('CC_gain').value)
        expected_vflthermtemp = sfl_functions.sfl_trhph_vfl_thermistor_temp(data_map.get(428).data)

        self.assertTrue(numpy.array_equal(stream_request.get_data_map().get(965).data, expected_vfltemp))
        self.assertTrue(numpy.array_equal(stream_request.get_data_map().get(966).data, expected_vflchlor))
        self.assertTrue(numpy.array_equal(stream_request.get_data_map().get(967).data, expected_vflorp))
        self.assertTrue(numpy.array_equal(stream_request.get_data_map().get(2623).data, expected_vflthermtemp))

    def test_multiple_streams(self):
        """

        :return:
        """
        thpsh_stream_request, thsph_coefficients = self.get_thsph_stream_request()
        trhph_stream_request, trhph_coefficients = self.get_trhph_stream_request()

        thpsh_stream_request.update(trhph_stream_request)
        thsph_coefficients.update(trhph_coefficients)
        interpolate(thpsh_stream_request)

        execute_dpas(thpsh_stream_request)

        for each in thpsh_stream_request.functions:
            self.assertIsNotNone(each.data)

    def test_interpolate(self):
        parameter = DataParameter(self.subsite, self.sensor, self.node,
                                  self.stream, self.method, Parameter.query.get(195))
        orig_times = [1, 2, 4, 5]
        new_times = [1, 2, 3, 4, 5]
        parameter.data = numpy.array([1, 2, 4, 5])
        parameter.times = orig_times
        parameter.interpolate(new_times)

        self.assertTrue(numpy.allclose(parameter.data, [1., 2., 3., 4., 5.]))

        parameter.data = numpy.array(['a', 'b', 'd', 'e'])
        parameter.interpolate(new_times)
        self.assertTrue(numpy.array_equal(parameter.data, ['a', 'b', 'b', 'd', 'e']))

        parameter.data = numpy.array(['a'])
        parameter.times = [1.0]
        parameter.interpolate(new_times)
        self.assertTrue(numpy.array_equal(parameter.data, ['a', 'a', 'a', 'a', 'a']))

        parameter.data = numpy.array([[1, 2, 3, 4, 5], [2, 3, 4, 5, 6]])
        parameter.times = numpy.array([1.0, 3.0])
        parameter.interpolate(numpy.array([1., 2., 3.]))
        self.assertTrue(numpy.allclose(parameter.data, [[1, 2, 3, 4, 5],
                                                        [1.5, 2.5, 3.5, 4.5, 5.5],
                                                        [2, 3, 4, 5, 6]]))

    def test_fetch_data(self):
        future = fetch_data(self.subsite, self.node, self.sensor, self.method, 'ctdbp_no_sample', 1, 9)
        data = future.result()
        self.assertTrue(len(data) == 9)

    def test_calculate(self):
        request = {
            "subsite": self.subsite,
            "node": self.node,
            "sensor": self.sensor,
            "method": self.method,
            "stream": "ctdbp_no_sample",
            "parameters": [3651]
        }
        coefficients = {
            "CC_a0": 1.0,
            "CC_a1": 1.0,
            "CC_a2": 1.0,
            "CC_a3": 1.0,
            "CC_lat": 1.0,
            "CC_lon": 1.0
        }

        result = json.loads(calculate(request, 1, 10, coefficients))

        # do the results contain our target product?
        key = u'3651'
        self.assertIn(key, result)

        # is it properly encoded as a dict?
        data = result[key]
        self.assertIsInstance(data, dict)

        # is the underlying data type a double?
        dtype = data['dtype']
        self.assertEqual(dtype, '<f8')

        # is the shape correct?
        self.assertEqual(data['shape'], [9])

        # can we decode the data back to a list
        self.assertIsInstance(data['data'], unicode)

        data = base64.b64decode(data['data'])
        self.assertIsInstance(data, str)

        data = msgpack.unpackb(data)
        self.assertIsInstance(data, list)

        # do the datatypes match?
        self.assertEqual(numpy.array(data).dtype.str, dtype)