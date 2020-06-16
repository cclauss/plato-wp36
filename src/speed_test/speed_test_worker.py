#!../../datadir_local/virtualenv/bin/python3
# -*- coding: utf-8 -*-
# speed_test_worker.py

"""
Run speed tests as requested through the RabbitMQ message queue
"""

import logging
import pika
import os
import json

import argparse
from plato_wp36 import lcsg_lc_reader, settings, results_logger, run_time_logger, task_timer

from plato_wp36.tda_wrappers import bls_reference, tls


def speed_test(lc_duration, tda_name, lc_filename):
    logging.info("Running <{lc_filename}> through <{tda_name}> with duration {lc_days:.1f}.".format(
        lc_filename=lc_filename,
        tda_name=tda_name,
        lc_days=lc_duration / 86400)
    )

    # Make sure that sqlite3 database exists to hold the run times for each transit detection algorithm
    time_log = run_time_logger.RunTimeLogger()
    result_log = results_logger.ResultsLogger()

    # Load lightcurve
    with task_timer.TaskTimer(tda_code=tda_name, target_name=lc_filename, task_name='load', lc_length=lc_duration,
                              time_logger=time_log):
        lc = lcsg_lc_reader.read_lcsg_lightcurve(
            filename=lc_filename,
            gzipped=True,
            cut_off_time=lc_duration / 86400
        )

    # Process lightcurve
    with task_timer.TaskTimer(tda_code=tda_name, target_name=lc_filename, task_name='proc', lc_length=lc_duration,
                              time_logger=time_log):
        if tda_name == 'tls':
            tls.process_lightcurve(lc, lc_duration / 86400)
            output = {}
        else:
            bls_reference.process_lightcurve(lc, lc_duration / 86400)
            output = {}

    # Send result to message queue
    result_log.record_timing(tda_code=tda_name, target_name=lc_filename, task_name='proc', lc_length=lc_duration,
                             result=output)

    # Close connection to message queue
    time_log.close()
    result_log.close()


def run_speed_tests(broker="amqp://guest:guest@rabbitmq-service:5672", queue="tasks"):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=broker))
    channel = connection.channel()

    channel.queue_declare(queue=queue)

    def callback(ch, method, properties, body):
        logging.info("--> Received {}".format(body))

        job_description = json.loads(body)
        speed_test(
            lc_duration=job_description['lc_duration'],
            tda_name=job_description['tda_name'],
            lc_filename=job_description['lc_filename']
        )

    channel.basic_consume(queue=queue, on_message_callback=callback, auto_ack=False)

    logging.info('Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()


if __name__ == "__main__":
    # Read commandline arguments
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()

    # Set up logging
    log_file_path = os.path.join(settings.settings['dataPath'], 'plato_wp36.log')
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s:%(filename)s:%(message)s',
                        datefmt='%d/%m/%Y %H:%M:%S',
                        handlers=[
                            logging.FileHandler(log_file_path),
                            logging.StreamHandler()
                        ])
    logger = logging.getLogger(__name__)
    logger.info(__doc__.strip())

    # Run speed tests
    run_speed_tests()