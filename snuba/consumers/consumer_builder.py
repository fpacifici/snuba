from batching_kafka_consumer import BatchingKafkaConsumer
from confluent_kafka import Producer
from typing import Sequence

from snuba.datasets.factory import get_dataset
from snuba.consumer import ConsumerWorker
from snuba import settings
from snuba import util


class ConsumerBuilder:
    """
    Simplifies the initialization of a batching consumer by merging
    parameters that generally come from the command line with defaults
    that come from the dataset class and defaults that come from the
    settings file.
    """

    def __init__(
        self,
        dataset_name: str,
        raw_topic: str,
        replacements_topic: str,
        max_batch_size: int,
        max_batch_time_ms: int,
        bootstrap_servers: Sequence[str],
        group_id: str,
        commit_log_topic: str,
        auto_offset_reset: str,
        queued_max_messages_kbytes: int,
        queued_min_messages: int,
        dogstatsd_host: str,
        dogstatsd_port: int
    ) -> None:
        self.dataset = get_dataset(dataset_name)
        self.dataset_name = dataset_name
        if not bootstrap_servers:
            self.bootstrap_servers = settings.DEFAULT_DATASET_BROKERS.get(
                dataset_name,
                settings.DEFAULT_BROKERS,
            )
        else:
            self.bootstrap_servers = bootstrap_servers

        self.raw_topic = raw_topic or self.dataset.get_default_topic()
        self.replacements_topic = replacements_topic or self.dataset.get_default_replacement_topic()
        self.commit_log_topic = commit_log_topic or self.dataset.get_default_commit_log_topic()

        self.producer = Producer({
            'bootstrap.servers': ','.join(bootstrap_servers),
            'partitioner': 'consistent',
            'message.max.bytes': 50000000,  # 50MB, default is 1MB
        })

        self.metrics = util.create_metrics(
            dogstatsd_host, dogstatsd_port, 'snuba.consumer',
            tags=[
                "group:%s" % group_id,
                "dataset:%s" % dataset_name,
            ]
        )

        self.max_batch_size = max_batch_size
        self.max_batch_time_ms = max_batch_time_ms
        self.group_id = group_id
        self.auto_offset_reset = auto_offset_reset
        self.queued_max_messages_kbytes = queued_max_messages_kbytes
        self.queued_min_messages = queued_min_messages

    def build_consumer(self) -> BatchingKafkaConsumer:
        """
        Builds the consumer with a ConsumerWorker.
        """

        return BatchingKafkaConsumer(
            self.raw_topic,
            worker=ConsumerWorker(
                self.dataset,
                producer=self.producer,
                replacements_topic=self.replacements_topic,
                metrics=self.metrics
            ),
            max_batch_size=self.max_batch_size,
            max_batch_time=self.max_batch_time_ms,
            metrics=self.metrics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            producer=self.producer,
            commit_log_topic=self.commit_log_topic,
            auto_offset_reset=self.auto_offset_reset,
            queued_max_messages_kbytes=self.queued_max_messages_kbytes,
            queued_min_messages=self.queued_min_messages,
        )