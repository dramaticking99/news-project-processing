import scrapy
from news_scraper.items import NewsArticleItem
from scrapy_playwright.page import PageMethod
import re
import json

class TheTimesOfIndiaSpider(scrapy.Spider):
    """
    Spider to scrape articles from The Times of India website.
    Uses Playwright to handle the dynamic, infinite-scroll nature of the homepage.
    """
    name = 'the_times_of_india'
    allowed_domains = ['timesofindia.indiatimes.com']
    start_urls = ['https://timesofindia.indiatimes.com/']

    def start_requests(self):
        """
        Initiates requests with Playwright to handle JavaScript rendering and scrolling.
        """
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    playwright_page_methods=[
                        # Wait for the page to be mostly loaded
                        PageMethod("wait_for_load_state", "domcontentloaded"),
                        # Scroll down to trigger infinite scroll
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        # Wait 3 seconds for new content to load
                        PageMethod("wait_for_timeout", 3000), 
                        # Scroll again to be sure
                        PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                        PageMethod("wait_for_timeout", 3000),
                    ],
                    errback=self.errback,
                ),
                callback=self.parse
            )

    async def parse(self, response):
        """
        Parses the main page to find all unique article links after scrolling.
        """
        page = response.meta.get("playwright_page")
        self.logger.info(f"Parsing list page: {response.url}")

        # Use a set to automatically handle duplicate links
        unique_links = set()

        # Gather links from various common layouts on the page
        selectors = [
            'li.BxDma > a.VeCXM::attr(href)',         # Main grid items
            'span.w_tle a::attr(href)',                # "Latest News" feed items
            'a.linktype1::attr(href)',                 # Other list items
            'a.linktype2::attr(href)',                 # Other list items
            'figure._YVis a.Hn2z7::attr(href)',         # Image-based links
        ]
        
        for selector in selectors:
            links = response.css(selector).getall()
            for link in links:
                # Ensure we only process valid, full URLs within the allowed domain
                if link and (link.startswith('/') or link.startswith('https://timesofindia.indiatimes.com')):
                    unique_links.add(response.urljoin(link))

        self.logger.info(f"Found {len(unique_links)} unique article links to scrape.")

        for link in unique_links:
            # We are interested in article pages, which typically contain '/articleshow/' or '/liveblog/'
            if '/articleshow/' in link or '/liveblog/' in link:
                yield scrapy.Request(
                    link,
                    callback=self.parse_article,
                    meta=dict(
                        playwright=True,
                        playwright_include_page=True,
                        errback=self.errback,
                    )
                )

        if page:
            await page.close()

    async def parse_article(self, response):
        """
        Scrapes data from an individual article page.
        """
        page = response.meta.get("playwright_page")
        self.logger.info(f"Scraping article: {response.url}")

        article = NewsArticleItem()
        article['url'] = response.url
        article['source_site'] = 'The Times of India'

        # --- Headline ---
        headline = response.css('h1.HNMDR::text').get()
        if not headline:
            headline = response.css('meta[property="og:title"]::attr(content)').get()
        article['headline'] = headline.strip() if headline else 'N/A'

        # --- Publication Date & Author (from JSON-LD is most reliable) ---
        publication_date = 'N/A'
        author = 'N/A'
        json_ld_scripts = response.css('script[type="application/ld+json"]::text').getall()
        for script in json_ld_scripts:
            try:
                data = json.loads(script)
                data_list = data if isinstance(data, list) else [data]
                for item in data_list:
                    if item.get('@type') == 'NewsArticle':
                        if item.get('datePublished') and publication_date == 'N/A':
                            publication_date = item['datePublished']
                        if item.get('author') and author == 'N/A':
                            author_data = item['author']
                            if isinstance(author_data, list) and author_data:
                                author = author_data[0].get('name', 'N/A')
                            elif isinstance(author_data, dict):
                                author = author_data.get('name', 'N/A')
                        if publication_date != 'N/A' and author != 'N/A':
                            break
                if publication_date != 'N/A' and author != 'N/A':
                    break
            except (json.JSONDecodeError, TypeError):
                continue
        
        # Fallback for author if not in JSON-LD
        if author == 'N/A':
            author = response.css('div.byline a::text').get()

        article['publication_date'] = publication_date
        article['author'] = author.strip() if author else 'N/A'
        
        # --- Body Text ---
        body_text_parts = response.css('div[data-articlebody="1"] ::text').getall()
        full_text = ' '.join(part.strip() for part in body_text_parts if part.strip())
        
        # Clean up common residual text
        if 'Disclaimer: This article is produced on behalf of' in full_text:
            full_text = full_text.split('Disclaimer: This article is produced on behalf of')[0]
        
        article['body_text'] = full_text.strip() if full_text else 'N/A'

        if page:
            await page.close()

        yield article

    async def errback(self, failure):
        """
        Handles errors that occur during the requests.
        """
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        self.logger.error(f"Request failed for {failure.request.url}: {failure.value}")