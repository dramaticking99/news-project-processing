# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy

class NewsArticleItem(scrapy.Item):
    url = scrapy.Field()
    headline = scrapy.Field()
    author = scrapy.Field()
    publication_date = scrapy.Field()
    body_text = scrapy.Field()
    source_site = scrapy.Field()