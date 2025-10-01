from playwright.sync_api import sync_playwright, Page, expect
import requests
import json
import time

# The URL of your FastAPI endpoint
API_URL = "[http://127.0.0.1:8000/process-article](http://127.0.0.1:8000/process-article)"
# The starting point for the scrape
START_URL = "[https://www.bbc.com/news](https://www.bbc.com/news)"

def send_to_api(article_data: dict):
    """Sends a dictionary of article data to the FastAPI server."""
    try:
        response = requests.post(API_URL, data=json.dumps(article_data), headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            print(f"✅ Successfully sent article to API: {article_data['title']}")
        else:
            print(f"❌ API Error: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Could not reach API: {e}")

def parse_article(page: Page):
    """Extracts title and content from a given article page."""
    try:
        # Wait for the main heading to be visible to ensure the page is loaded
        heading_locator = page.locator('h1#main-heading')
        expect(heading_locator).to_be_visible(timeout=10000)

        title = heading_locator.inner_text()

        # Combine text from all relevant paragraph blocks
        paragraphs = page.locator('div[data-component="text-block"] p').all_inner_texts()
        content = " ".join(paragraphs)

        if not title or not content:
            print(f"⚠️  Could not extract full content from {page.url}")
            return None

        return {
            'url': page.url,
            'title': title,
            'content': content
        }
    except Exception as e:
        print(f"Error parsing article {page.url}: {e}")
        return None

def run_scraper():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # Set headless=True for production
        page = browser.new_page()

        print(f"Navigating to {START_URL}...")
        page.goto(START_URL, wait_until='domcontentloaded')

        # This selector is an example for BBC News, it will likely need to be updated.
        # It looks for links that start with /news/ and have a specific data-testid.
        article_links = page.locator('a[href^="/news/"][data-testid="internal-link"]').all()

        print(f"Found {len(article_links)} potential article links.")

        # Limit to a few articles for this example
        for i, link_locator in enumerate(article_links[:5]):
            href = link_locator.get_attribute('href')
            article_url = page.urljoin(href)

            print(f"\n[{i+1}/5] Scraping: {article_url}")

            article_page = browser.new_page()
            try:
                article_page.goto(article_url, wait_until='domcontentloaded')
                article_data = parse_article(article_page)
                if article_data:
                    send_to_api(article_data)
            except Exception as e:
                print(f"Could not navigate to or process page {article_url}: {e}")
            finally:
                article_page.close()
                time.sleep(1) # Be a polite scraper

        print("\nScraping finished.")
        browser.close()

if __name__ == "__main__":
    run_scraper()