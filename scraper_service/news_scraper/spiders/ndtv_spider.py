# scraper_service/news_scraper/spiders/ndtv_spider.py

import scrapy
from scrapy_playwright.page import PageMethod
from news_scraper.items import NewsArticleItem
from datetime import datetime
import pytz
import re

def should_abort_request(request):
    """
    Blocks non-essential resources like images, fonts, and tracking scripts
    to speed up page loads.
    """
    if request.resource_type in ("image", "stylesheet", "font", "media"):
        return True
    
    tracking_domains = [
        "google-analytics.com", "googletagmanager.com", "scorecardresearch.com",
        "chartbeat.com", "cxense.com", "adservice.google.com", "doubleclick.net",
        "facebook.net", "twitter.com", "googlesyndication.com", "vdo.ai"
    ]
    for domain in tracking_domains:
        if domain in request.url:
            return True
            
    return False


class NdtvSpider(scrapy.Spider):
    name = 'ndtv'
    allowed_domains = ['ndtv.com']
    
    custom_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    }

    async def start(self):
        url = 'https://www.ndtv.com/world-news'
        yield scrapy.Request(
            url,
            headers=self.custom_headers,
            meta=dict(
                playwright=True,
                playwright_include_page=True,
                playwright_page_methods=[
                    PageMethod("route", re.compile(r".*"), 
                             lambda route: route.abort() if should_abort_request(route.request) else route.continue_()),
                    PageMethod("wait_for_selector", "div.news_Itm"),
                ],
                playwright_page_goto_kwargs={
                    "wait_until": "commit",  # Using the fastest wait condition
                },
                errback=self.errback,
            )
        )

    async def parse(self, response):
        page = response.meta.get("playwright_page")
        
        self.logger.info(f"Parsing list page: {response.url}")

        article_links = response.css('div.news_Itm_img a::attr(href)').getall()
        self.logger.info(f"Found {len(article_links)} article links to scrape.")

        for link in article_links:
            if not link.startswith('https://www.ndtv.com'):
                continue
            
            yield scrapy.Request(
                link, 
                callback=self.parse_article,
                headers=self.custom_headers,
                meta=dict(
                    playwright=True,
                    playwright_page_methods=[
                        PageMethod("route", re.compile(r".*"), 
                                 lambda route: route.abort() if should_abort_request(route.request) else route.continue_()),
                        PageMethod("wait_for_selector", "div.sp-cn"),
                    ],
                    playwright_page_goto_kwargs={
                        "wait_until": "commit",
                    },
                )
            )
            
        next_page = response.css('a.btn_np:contains("NEXT")::attr(href)').get()
        if next_page:
            self.logger.info(f"Found next page: {next_page}")
            if page:
                await page.close()
            
            yield scrapy.Request(
                next_page, 
                callback=self.parse,
                headers=self.custom_headers,
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    playwright_page_methods=[
                        PageMethod("route", re.compile(r".*"), 
                                 lambda route: route.abort() if should_abort_request(route.request) else route.continue_()),
                        PageMethod("wait_for_selector", "div.news_Itm"),
                    ],
                    playwright_page_goto_kwargs={
                        "wait_until": "commit",
                    },
                    errback=self.errback,
                )
            )
        else:
            self.logger.info("No more pages to scrape. Finishing.")
            if page:
                await page.close()

    async def parse_article(self, response):
        self.logger.info(f"Scraping article: {response.url}")
        
        item = NewsArticleItem()
        item['url'] = response.url
        item['source_site'] = 'NDTV'
        
        headline = response.css('h1.sp-ttl::text').get()
        item['headline'] = headline.strip() if headline else ''

        date_str = response.css('span[itemprop="dateModified"]::attr(content)').get()
        if date_str:
            try:
                dt_object = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
                item['publication_date'] = dt_object.isoformat()
            except ValueError:
                self.logger.warning(f"Could not parse date: {date_str}")
                item['publication_date'] = None
        else:
            item['publication_date'] = None

        authors = response.css('nav.pst-by a.pst-by_lnk::text').getall()
        item['author'] = ', '.join(au.strip() for au in authors) if authors else 'NDTV Correspondent'

        body_paragraphs = response.css('div[itemprop="articleBody"] p::text').getall()
        item['body_text'] = '\n'.join([para.strip() for para in body_paragraphs if para.strip()])
        
        yield item

    async def errback(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        self.logger.error(f"Playwright request failed: {failure.value}")