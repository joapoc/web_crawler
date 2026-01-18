import argparse
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from collections import deque
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

visited_lock = threading.Lock()
visited = set()
found_paths = set()


def normalize_url(url):
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def is_same_domain(url, base_domain):
    parsed = urlparse(url)
    return parsed.netloc == base_domain or parsed.netloc.endswith(f".{base_domain}")


def extract_links(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    
    for tag in soup.find_all(['a', 'link', 'script', 'img', 'form']):
        url = None
        if tag.name == 'a':
            url = tag.get('href')
        elif tag.name == 'link':
            url = tag.get('href')
        elif tag.name == 'script':
            url = tag.get('src')
        elif tag.name == 'img':
            url = tag.get('src')
        elif tag.name == 'form':
            url = tag.get('action')
        
        if url:
            absolute_url = urljoin(base_url, url)
            links.add(absolute_url)
    
    return links


def fetch_url(url, timeout=10):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        return response.text, response.status_code
    except requests.RequestException as e:
        return None, None


def crawl_url(url, base_domain, depth, max_depth):
    if depth > max_depth:
        return set()
    
    normalized = normalize_url(url)
    
    with visited_lock:
        if normalized in visited:
            return set()
        visited.add(normalized)
    
    if not is_same_domain(url, base_domain):
        return set()
    
    content, status = fetch_url(url)
    
    parsed = urlparse(url)
    path = parsed.path or '/'
    
    with visited_lock:
        found_paths.add((path, status))
    
    print(f"[{status}] {url}")
    
    if content is None:
        return set()
    
    links = extract_links(content, url)
    return links


def crawl(start_url, max_depth=3, max_workers=10):
    parsed = urlparse(start_url)
    base_domain = parsed.netloc
    
    print(f"\n{'='*60}")
    print(f"Starting crawl: {start_url}")
    print(f"Base domain: {base_domain}")
    print(f"Max depth: {max_depth}")
    print(f"{'='*60}\n")
    
    queue = deque([(start_url, 0)])
    
    while queue:
        current_batch = []
        current_depth = queue[0][1] if queue else 0
        
        while queue and queue[0][1] == current_depth:
            current_batch.append(queue.popleft())
        
        if current_depth > max_depth:
            break
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(crawl_url, url, base_domain, depth, max_depth): (url, depth)
                for url, depth in current_batch
            }
            
            for future in as_completed(futures):
                new_links = future.result()
                for link in new_links:
                    normalized = normalize_url(link)
                    with visited_lock:
                        if normalized not in visited and is_same_domain(link, base_domain):
                            queue.append((link, current_depth + 1))
    
    return found_paths


def print_results(paths):
    print(f"\n{'='*60}")
    print(f"DISCOVERED PATHS ({len(paths)} total)")
    print(f"{'='*60}\n")
    
    sorted_paths = sorted(paths, key=lambda x: x[0])
    
    for path, status in sorted_paths:
        status_indicator = "✓" if status and 200 <= status < 300 else "✗"
        print(f"  {status_indicator} [{status}] {path}")


def main():
    parser = argparse.ArgumentParser(
        description='Web Directory Traversal & Crawler Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler.py https://example.com
  python crawler.py https://example.com -d 5 -w 20
  python crawler.py https://example.com --depth 3 --workers 10
        """
    )
    
    parser.add_argument('url', help='Target URL to crawl')
    parser.add_argument('-d', '--depth', type=int, default=3,
                        help='Maximum crawl depth (default: 3)')
    parser.add_argument('-w', '--workers', type=int, default=10,
                        help='Number of concurrent workers (default: 10)')
    parser.add_argument('-o', '--output', type=str,
                        help='Output file to save results')
    
    args = parser.parse_args()
    
    if not args.url.startswith(('http://', 'https://')):
        args.url = 'https://' + args.url
    
    try:
        paths = crawl(args.url, max_depth=args.depth, max_workers=args.workers)
        print_results(paths)
        
        if args.output:
            with open(args.output, 'w') as f:
                for path, status in sorted(paths):
                    f.write(f"{status}\t{path}\n")
            print(f"\nResults saved to: {args.output}")
            
    except KeyboardInterrupt:
        print("\n\nCrawl interrupted by user.")
        print_results(found_paths)
        sys.exit(0)


if __name__ == '__main__':
    main()