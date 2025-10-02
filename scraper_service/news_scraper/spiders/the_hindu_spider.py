import scrapy
from news_scraper.items import NewsArticleItem
from scrapy_playwright.page import PageMethod
import re

def should_abort_request(request):
    """
    Helper function to decide if a request should be aborted.
    Blocks images, stylesheets, fonts, and tracking scripts.
    """
    if request.resource_type in ("image", "stylesheet", "font"):
        return True
    # Block requests to common tracking/ad domains
    tracking_domains = [
        "google-analytics.com", "googletagmanager.com", "scorecardresearch.com",
        "chartbeat.com", "cxense.com", "adservice.google.com", "doubleclick.net"
    ]
    for domain in tracking_domains:
        if domain in request.url:
            return True
    return False


class TheHinduSpider(scrapy.Spider):
    """
    Spider to scrape articles from The Hindu's 'latest-news' section.
    Uses Playwright and handles pagination to scrape multiple pages.
    """
    name = 'the_hindu'
    allowed_domains = ['thehindu.com']

    async def start(self):
        """
        This is the entry point for the spider. It generates the first request.
        """
        url = 'https://www.thehindu.com/latest-news/'
        yield scrapy.Request(
            url,
            callback=self.parse,
            meta=dict(
                playwright=True,
                playwright_include_page=True,
                playwright_page_methods=[
                    PageMethod("route", re.compile(r".*"), lambda route: route.abort() if should_abort_request(route.request) else route.continue_()),
                    PageMethod('wait_for_selector', 'ul.timeline-with-img')
                ],
                errback=self.errback,
            )
        )

    async def parse(self, response):
        """
        This method finds article links on the current page, yields requests
        for them, and then finds the 'Next' page link to continue crawling.
        """
        page = response.meta.get("playwright_page")
        
        self.logger.info(f"Parsing list page: {response.url}")

        article_links = response.css('ul.timeline-with-img h3.title > a::attr(href)').getall()

        if not article_links:
            self.logger.warning(f"No article links found on page: {response.url}. The website layout may have changed.")
        else:
             self.logger.info(f"Found {len(article_links)} article links to scrape.")

        for link in article_links:
            yield response.follow(link, callback=self.parse_article)

        # --- PAGINATION LOGIC ---
        # Find the 'Next' button's link
        next_page_url = response.css('a.page-link.next::attr(href)').get()
        if next_page_url:
            self.logger.info(f"Found next page: {next_page_url}")
            # Close the current page *before* making the next request to save resources
            if page:
                await page.close()
            # Follow the link to the next page, and call this same 'parse' method on it
            yield response.follow(
                next_page_url, 
                callback=self.parse,
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    playwright_page_methods=[
                        PageMethod("route", re.compile(r".*"), lambda route: route.abort() if should_abort_request(route.request) else route.continue_()),
                        PageMethod('wait_for_selector', 'ul.timeline-with-img')
                    ],
                    errback=self.errback,
                )
            )
        else:
            self.logger.info("No more pages to scrape. Finishing.")
            if page:
                await page.close()

    def parse_article(self, response):
        """
        This method scrapes the data from the individual article page.
        """
        self.logger.info(f"Scraping article: {response.url}")

        article = NewsArticleItem()
        article['url'] = response.url
        article['headline'] = response.css('h1.title::text').get('').strip()
        article['author'] = response.css('div.author-details a.person-name::text').get('').strip()
        article['publication_date'] = response.css('meta[property="article:published_time"]::attr(content)').get('').strip()
        
        body_paragraphs = response.css('div[id*="content-body-"] p::text').getall()
        article['body_text'] = " ".join(p.strip() for p in body_paragraphs).strip()
        article['source_site'] = 'The Hindu'

        yield article

    async def errback(self, failure):
        """
        Handles errors in the Playwright request.
        """
        page = failure.request.meta["playwright_page"]
        await page.close()
        self.logger.error(f"Playwright request failed: {failure.value}")