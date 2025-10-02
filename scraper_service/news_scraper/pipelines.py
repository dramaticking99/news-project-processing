# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

import pymongo

class MongoPipeline:
    collection_name = 'news_articles'

    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db

    @classmethod
    def from_crawler(cls, crawler):
        return cls (
            mongo_uri = crawler.settings.get('MONGO_URI'),
            mongo_db = crawler.settings.get('MONGO_DB', 'news_data')
        )
    
    def open_spider(self, spider):
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        spider.logger.info("MongoDb Connection Opened.")

    def close_spider(self, spider):
        self.client.close()
        spider.logger.info("MongoDb Connection Closed.")

    def process_item(self, item, spider):
        # Using the url as the unique identifier to avoid duplcations
        self.db[self.collection_name].update_one(
            {'url': item['url']},
            {'$set': dict(item)},
            upsert=True
        )
        spider.logger.info(f"Saved article to MongoDB: {item['headline']}")
        return item