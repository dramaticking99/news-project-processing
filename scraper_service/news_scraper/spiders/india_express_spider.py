import scrapy
from scrapy_playwright.page import PageMethod
from news_scraper.items import NewsArticleItem
import json

class IndianExpressSpider(scrapy.Spider):
    """
    Spider to scrape articles from The Indian Express website.
    It uses Playwright on the homepage to ensure all dynamic content is loaded,
    then uses standard Scrapy requests for individual articles for efficiency.
    """
    name = 'indian_express'
    allowed_domains = ['indianexpress.com']
    start_urls = ['https://indianexpress.com/']

    def start_requests(self):
        """
        Initiates requests with Playwright to handle JavaScript rendering on the homepage.
        """
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta=dict(
                    playwright=True,
                    playwright_include_page=True,
                    playwright_page_methods=[
                        # Wait for the page structure to be ready
                        PageMethod("wait_for_load_state", "domcontentloaded"),
                    ],
                    errback=self.errback,
                ),
                callback=self.parse
            )

    async def parse(self, response):
        """
        Parses the homepage to find all unique article links.
        """
        page = response.meta.get("playwright_page")
        self.logger.info(f"Parsing list page: {response.url}")

        # A set automatically handles duplicate links
        unique_links = set()
        
        # A list of selectors to find article links in various sections
        link_selectors = [
            'div.lead-stories a::attr(href)',
            'div.top-news a::attr(href)',
            'div.other-article a::attr(href)',
            'div.other-story a::attr(href)',
            'div.small-story a::attr(href)',
            'div.news h4 a::attr(href)'
        ]
        
        for selector in link_selectors:
            links = response.css(selector).getall()
            for link in links:
                # Ensure the link is valid and within the allowed domain
                if link and (link.startswith('/') or link.startswith('https://indianexpress.com')):
                    unique_links.add(response.urljoin(link))

        self.logger.info(f"Found {len(unique_links)} unique article links to scrape.")

        for link in unique_links:
            # We are only interested in article pages
            if '/article/' in link:
                # Standard Scrapy request is faster for simple article pages
                yield scrapy.Request(
                    link,
                    callback=self.parse_article,
                    meta=dict(errback=self.errback)
                )
        
        # Close the Playwright page after we are done with it
        if page:
            await page.close()

    async def parse_article(self, response):
        """
        Scrapes data from an individual article page.
        """
        self.logger.info(f"Scraping article: {response.url}")

        article = NewsArticleItem()
        article['url'] = response.url
        article['source_site'] = 'The Indian Express'

        # --- Publication Date & Author (from JSON-LD is most reliable) ---
        publication_date = 'N/A'
        author = 'N/A'
        
        try:
            # Find the structured data script
            json_ld_script = response.css('script[type="application/ld+json"]::text').get()
            if json_ld_script:
                data = json.loads(json_ld_script)
                # Data can be a single object or a list within a '@graph' key
                data_list = data.get('@graph', [data])
                
                for item in data_list:
                    if item.get("@type") == "NewsArticle":
                        publication_date = item.get('datePublished', 'N/A')
                        author_data = item.get('author')
                        if isinstance(author_data, list) and author_data:
                            author = author_data[0].get('name', 'N/A')
                        elif isinstance(author_data, dict):
                            author = author_data.get('name', 'N/A')
                        break # Exit loop once we find the main article data
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Could not parse JSON-LD for {response.url}: {e}")

        # --- Headline ---
        headline = response.css('h1.native_story_title::text').get()
        # Fallback to meta tag if the h1 is not found
        if not headline:
            headline = response.css('meta[property="og:title"]::attr(content)').get()
        
        article['headline'] = headline.strip() if headline else 'N/A'
        article['publication_date'] = publication_date
        article['author'] = author.strip() if author else 'N/A'
        
        # --- Body Text ---
        body_parts = response.css('div.story_details p::text').getall()
        full_text = ' '.join(part.strip() for part in body_parts if part.strip())
        article['body_text'] = full_text if full_text else 'N/A'

        yield article

    async def errback(self, failure):
        """
        Handles errors that occur during requests.
        """
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        self.logger.error(f"Request failed for {failure.request.url}: {failure.value}")