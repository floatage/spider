#encoding=utf-8

from scrapy.spiders import CrawlSpider, Rule, Spider, Request
from scrapy.linkextractors import LinkExtractor
from scrapy.xlib.pydispatch import dispatcher
from scrapy import signals
import re, json, logging, os, sqlite3, cx_Oracle

from froag.items import NewsItem

os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'
# DB_CONNECT_STRING_ORACLE = 'foragCollecter_1/foragCollecter@10.18.50.229/orcl'
DB_CONNECT_STRING_ORACLE = 'foragCollecter_1/foragCollecter@192.168.1.181/orcl'
SQL_ORACLE_ADD_RELATION = 'INSERT INTO foragOwner.UrlRelation(sourceUrl,parentUrl) VALUES(:1,:2)'
SQL_ORACLE_ADD_SIMILARURL = 'INSERT INTO foragOwner.SimilarUrl(sourceUrl,similarUrl) VALUES(:1,:2)'

def storeDataList_db_oracle(database, dataList, sql):
    cursor = database.cursor()
    cursor.prepare(sql)
    
    for item in dataList:
        try:
            cursor.execute(None, item)
        except cx_Oracle.IntegrityError:
            pass 
    
    database.commit()
    dataList.clear()
    
def storeItemExtraInfor_db_oracle(url_relations, similar_news_urls):
    urLen, snuLen = len(url_relations), len(similar_news_urls)
    if urLen > 0 or snuLen > 0:
        database = cx_Oracle.connect(DB_CONNECT_STRING_ORACLE)
        if urLen > 0: storeDataList_db_oracle(database, url_relations, SQL_ORACLE_ADD_RELATION)
        if snuLen > 0: storeDataList_db_oracle(database, similar_news_urls, SQL_ORACLE_ADD_SIMILARURL)
        database.close()

def responseStrGenerator(response, selector, isEncoding=False, encoding='utf-8', pos=1, getPart=False):
    tags = response.css(selector)
    if getPart: tags = tags[0:pos]
    result = (' '.join(tags.extract())).strip()
    if isEncoding:
        result = result.encode(encoding);
    return result

class HuanqiuSpider(Spider):
    name = 'huanqiu'
    default_author_name = '环球网'
    allowed_domains = []
    start_urls = [
        'http://www.huanqiu.com/'
    ]
    
    url_pattern_article = 'http://.*\.huanqiu\.com/.*\.html'
    url_pattern_sub = 'http://.*\.huanqiu\.com/.*/'
    sub_website = set()
    
    item_content_delete_tag = ['div', 'script']
    item_content_tag_class = '.text'
    item_content_unfeature_tag = []
    
    url_relations = []
    similar_news_urls = []
    item_counter = 0
    item_store_number = 400
    item_store_counter = 0
    
    request_url_recent = set()
    
    FILTER_SUBWEBSITE = True
    STORE_URLRELATIONS = True
    STORE_SIMILARURLS = True
    
    DB_NAME = "similarUrls.db"
    SQL_CREATE_TABLE_SimilarUrl = '''CREATE TABLE IF NOT EXISTS SimilarUrl(url text,similarUrl text,primary key(url,similarUrl))'''
    SQL_ADD_SIMILARURL = "INSERT INTO SimilarUrl(url,similarUrl) VALUES(?,?)"
    
    def parse(self, response):
        item = NewsItem()
        item['msource'] = response.url
        item['mtags'] = responseStrGenerator(response, '.topPath a:nth-of-type(2)::text')
        item['mtitle'] = responseStrGenerator(response, '.conText h1::text')
        item['mtime'] = responseStrGenerator(response, '.conText .summaryNew .timeSummary::text')
        item['mauthor'] = responseStrGenerator(response, '.conText .summaryNew .fromSummary a::text')
        item['mcontent'] = responseStrGenerator(response, '.conText .text')
        item['mintro'] = responseStrGenerator(response, '.conText .text p:first-of-type::text')
        item['mpic'] = responseStrGenerator(response, '.conText .text img:first-of-type::attr(src)', getPart=True)   
        yield item
        
        self.item_counter = self.item_counter + 1  
        if self.item_counter % self.item_store_number == 0:
            self.storeItemExtraInfor()
            self.request_url_recent.clear()
        
        if self.STORE_SIMILARURLS: self.getSimilarNewUrl(response, response.url)
        
        parentUrl = response.url
        next_pages = response.css('a::attr("href")').extract()
        for next_page in next_pages:
            next_page = response.urljoin(next_page)
            
            if re.match(self.url_pattern_article, next_page) and next_page not in self.request_url_recent:
                self.request_url_recent.add(next_page)
                if self.STORE_URLRELATIONS: self.url_relations.append((str(next_page), str(parentUrl)))
                yield Request(next_page, callback=self.parse)
            elif self.FILTER_SUBWEBSITE and re.match(self.url_pattern_sub, next_page) and next_page not in self.sub_website:
                self.sub_website.add(next_page)
                yield Request(next_page, callback=self.parse)
    
    def getSimilarNewUrl(self, response, url):
        similar_urls = response.css('.reTopics .listText ul a::attr("href")').extract()
        similar_urls = [response.urljoin(url) for url in similar_urls]
        if isinstance(similar_urls, list) and len(similar_urls) > 0:
            url = str(url)
            for surl in similar_urls:
                self.similar_news_urls.append((url, str(surl)))
    
    def storeItemExtraInfor(self):
        storeItemExtraInfor_db_oracle(self.url_relations, self.similar_news_urls)
          
    def storeUrls(self, way='db'):
        if way == 'db':
            self.storeUrls_db()
    
    def storeUrls_db(self):
        database = sqlite3.connect(self.DB_NAME)
        self.log('store similarUrl start', logging.INFO)
        for key, value in self.similar_news_urls.items():
            for listItem in value:
                try:
                    database.execute(self.SQL_ADD_SIMILARURL, (str(key), str(listItem)))
                except sqlite3.IntegrityError:
                    pass
        database.commit()
        self.similar_news_urls.clear()
        self.log('store similarUrl commit', logging.INFO)
        database.close()
    
    #     def __init__(self):
#         self.createTable()
    
    def createTable(self):
        try:
            database = sqlite3.connect(self.DB_NAME)
            database.execute(self.SQL_CREATE_TABLE_SimilarUrl)
            database.commit()
            database.close()
        except sqlite3.Error:
            self.log("create SimilarUrls table error", logging.WARN)
    
    def close(self):
#         self.storeUrls()
        self.storeItemExtraInfor()
        
    
class CSDNSpider(Spider):
    name = 'csdn'
    default_author_name = 'csdn'
    allowed_domains = []
    start_urls = [
        'http://blog.csdn.net/'
#         'http://blog.csdn.net/u012468376/article/details/55001497'
    ]
    
    url_pattern_article = 'http://blog\.csdn\.net/.*/article/details/.*'
#     http://blog.csdn.net/guolin_blog/article/details/70215985
#     http://blog.csdn.net/u012468376/article/category/6083852
#     http://blog.csdn.net/enterprise/newarticle.html
#     http://blog.csdn.net/column/details/objective-c-primary.html
#     http://blog.csdn.net/VNanyesheshou
    url_pattern_sub = 'http://blog\.csdn\.net/.*'
    sub_website = set()
    
    item_content_delete_tag = ['script']
    item_content_tag_class = '.article_content'
    
    item_counter = 0
    item_store_number = 400
    item_store_counter = 0
    
    request_url_recent = set()
    
    FILTER_SUBWEBSITE = True
    STORE_SIMILARURLS = True
    
    defaul_tag_weight = 10.0
    max_tag_number = 5
    
    def _getItemTags(self, tags, classfy):
        tags = tags.split(' ')
        tags.extend(classfy.split(' '))
        result = {"type": self.default_author_name, "tag":{}}
        
        for tag in tags:
            if tag != '':
                tag = tag.capitalize()
                result['tag'][tag] = result['tag'].setdefault(tag, 0.0) + self.defaul_tag_weight  
        
        if len(result['tag']) != 0:
            tags = sorted(result['tag'].items(), key=lambda x:x[1], reverse=True)
            tags = tags[0:min(len(result['tag']), self.max_tag_number)]
            result['tag'] = {x[0]:x[1] for x in tags}
        return json.dumps(result, ensure_ascii=False)
    
    def parse(self, response):
        item = NewsItem()
        item['mauthor'] = ''
        item['msource'] = response.url
        tags = responseStrGenerator(response, '.link_categories a::text')
        classfy = responseStrGenerator(response, '.category_r label span::text')
        item['mtags'] = self._getItemTags(tags, classfy)
        item['mtitle'] = responseStrGenerator(response, '.link_title a::text')
        item['mtime'] = responseStrGenerator(response, '.article_r .link_postdate::text')
        item['mcontent'] = responseStrGenerator(response, '.article_content')
        item['mintro'] = responseStrGenerator(response, '.article_content p:first-of-type::text')
        item['mpic'] = responseStrGenerator(response, '.article_content img:first-of-type::attr(src)', getPart=True)   
        yield item
        
        self.item_counter = self.item_counter + 1  
        if self.item_counter % self.item_store_number == 0:
            self.request_url_recent.clear()
        
        next_pages = response.css('a::attr("href")').extract()
        for next_page in next_pages:
            next_page = response.urljoin(next_page)
            
            if re.match(self.url_pattern_article, next_page) and next_page not in self.request_url_recent:
                self.request_url_recent.add(next_page)
                yield Request(next_page, callback=self.parse)
            elif self.FILTER_SUBWEBSITE and re.match(self.url_pattern_sub, next_page) and next_page not in self.sub_website:
                self.sub_website.add(next_page)
                yield Request(next_page, callback=self.parse)
    
class EastdaySpider(Spider):
    name = 'eastday'
    default_author_name = '东方头条'
    allowed_domains = ['mini.eastday.com']
    start_urls = [
        'https://mini.eastday.com'
    ]
    url_pattern = 'https://mini\.eastday\.com/a/.*'
    
    item_content_delete_tag = []
    item_content_tag_class = '.J-contain_detail_cnt'
    item_counter = 0
    item_min_number = 0
    item_store_number = 600
    item_store_counter = 0
    url_relations = {}
    url_relations_filename = "urlRelations.json"

    DB_NAME = "urlRelations.db"
    SQL_CREATE_TABLE_UrlRelation = '''CREATE TABLE IF NOT EXISTS UrlRelation(url text,parentUrl text,primary key(url,parentUrl))'''
    SQL_ADD_RELATION = "INSERT INTO UrlRelation(url,parentUrl) VALUES(?,?)"

#     def __init__(self):
#         self.createTable()
    
    def storeUrlRelations(self, way="db"):
        if way == "file":
            self.storeUrlRelations_file()
        elif way == "db":
            self.storeUrlRelations_db()
    
    def createTable(self):
        try:
            database = sqlite3.connect(self.DB_NAME)
            database.execute(self.SQL_CREATE_TABLE_UrlRelation)
            database.commit()
            database.close()
        except sqlite3.Error:
            self.log("create UrlRelation table error", logging.WARN)
    
#     def executeSQL(self, sql, isComment, key, value):
#         try:
#             database = sqlite3.connect(self.DB_NAME)
#             print('store relation start')
#             database.execute(sql, (key, value))
#             print('store relation execute')
#             if isComment: 
#                 database.commit()
#                 database.close()
#                 print('store relation commit')
#         except sqlite3.Error:
#             print('store relation error')
#             self.log("store relations error", logging.WARN)
    
    def storeUrlRelations_db(self):
        database = sqlite3.connect(self.DB_NAME)
        self.log('store relation start', logging.INFO)
        for key, value in self.url_relations.items():
            for listItem in value:
                try:
                    database.execute(self.SQL_ADD_RELATION, (str(key), str(listItem)))
                except sqlite3.IntegrityError:
                    pass
        database.commit()
        self.url_relations.clear()
        self.log('store relation commit', logging.INFO)
        database.close()
    
    def insert_url(self, url, parentUrl, unique):
        parentUrls = parentUrl if isinstance(parentUrl, list) else [parentUrl]
        if url in self.url_relations:
            self.url_relations[url].extend(parentUrls)
        else:
            self.url_relations[url] = parentUrls
        
        if unique:
            self.url_relations[url] = list({}.fromkeys(self.url_relations[url]).keys())
    
    def storeUrlRelations_file(self):
        try:
            url_relations_recent = {}
            if os.path.exists(self.url_relations_filename):
                file = open(self.url_relations_filename, 'r')
                fileContent = file.read()
                file.close()
                file = open(self.url_relations_filename, 'w')
                
                try:
                    url_relations_recent = json.loads(fileContent)
                except json.decoder.JSONDecodeError:
                    pass
                              
            else:
                file = open(self.url_relations_filename, 'w')
            
            for key, value in url_relations_recent.items():
                self.insert_url(key, value, True)
            
            json.dump(self.url_relations, file, indent=4, separators=(',', ': '))
            self.item_store_counter = self.item_store_counter + 1
            
            self.url_relations.clear()
        except IOError:
            self.log('url relations file IOError', logging.ERROR)
        finally:
            file.close()
        
#     def close(self):
#         self.storeUrlRelations()
    
    def parse(self, response):
        
        item = NewsItem()
        item['msource'] = response.url
        item['mtags'] = responseStrGenerator(response, '.detail_position a:nth-of-type(3)::text')
        item['mtitle'] = responseStrGenerator(response, '.title_detail h1 span:first-of-type::text')
        item['mtime'] = responseStrGenerator(response, '.fl i:first-of-type::text')
        item['mauthor'] = responseStrGenerator(response, '.fl i:last-of-type::text')
        item['mcontent'] = responseStrGenerator(response, '.J-contain_detail_cnt')
        item['mintro'] = responseStrGenerator(response, '.J-contain_detail_cnt p:first-of-type::text')
        item['mpic'] = responseStrGenerator(response, '.J-contain_detail_cnt img:first-of-type::attr(src)', True)
                
        yield item
        self.item_counter = self.item_counter + 1  
        
#         if self.item_counter % self.item_store_number == 0:
#             self.storeUrlRelations()
        
#         parentUrl = response.url
        next_pages = response.css('a::attr("href")').extract()
        for next_page in next_pages:
            next_page = response.urljoin(next_page)
            if re.match(self.url_pattern, next_page):
#                 self.insert_url(next_page, parentUrl, False)
                yield Request(next_page, callback=self.parse)

class CEastdaySpider(CrawlSpider): 
    name = "ceastday" 
    website_possible_httpstatus_list = [403]
    handle_httpstatus_list = [403]
    
    allowed_domains = ["mini.eastday.com"] 
    start_urls = [
        "https://mini.eastday.com"
    ]
    rules = [
            Rule(LinkExtractor(allow=(r'https://mini\.eastday\.com/a/.*')), callback='page_handle')
    ]
    #r'https://mini\.eastday\.com/a/.*\.html'
#     allowed_domains = ["thepaper.cn"] 
#     start_urls = [
#         "http://www.thepaper.cn/"
#     ]
#     rules = [
#         Rule(LinkExtractor(allow=(r'http://www\.thepaper\.cn/newsDetail.*')), callback='pengpai_handle')
#     ]

#     allowed_domains = ["qidian.com"] 
#     start_urls = [
#         "http://www.qidian.com/"
#     ]
#     rules = [
#         Rule(LinkExtractor(allow=(r'http://book\.qidian\.com/info/.*')), callback='qidian_handle')
#     ]
 
    url_queue = []
    counter = 20
    counter_max = 20
     
    def page_handle(self, response): 
#         if response.body == "banned":
#             req = response.request
#             req.meta["change_proxy"] = True
#             yield req
#         else:
        
#         if self.counter == 0:
#             response.request.meta["change_proxy"] = True
#             self.counter = self.counter_max
#             
#         self.counter -= 1
        
        item = NewsItem()
        self.url_queue.append(response.url)
        item['msource'] = response.url
        item['mtitle'] = ' '.join(response.css('.title_detail h1 span:first-of-type::text').extract()).strip()
        item['mcontent'] = ' '.join(response.css('.J-contain_detail_cnt').extract()).strip()
        item['mintro'] = ' '.join(response.css('.J-contain_detail_cnt p:first-of-type::text').extract()).strip()
        item['mpic'] = ' '.join(response.css('.J-contain_detail_cnt img:first-of-type::attr(src)').extract()).strip()
        item['mtags'] = ' '.join(response.css('.detail_position a:nth-of-type(3)::text').extract()).strip()
        return item
    
    def pengpai_handle(self, response):
        if self.counter == 0:
            response.request.meta["change_proxy"] = True
            self.counter = self.counter_max
             
        self.counter -= 1
        
        item = NewsItem()
        item['msource'] = response.url
        item['mtitle'] = response.css('.news_title').extract()
        item['mcontent'] = response.css('.news_txt').extract()
        item['mintro'] = response.css('.news_txt p:first-of-type').extract()
        item['mpic'] = response.css('.J-news_txt img:first-of-type').extract()
        item['mtags'] = response.css('.news_path a:nth-of-type(2)').extract()
        return item
    
    def qidian_handle(self, response):
        self.url_queue.append(response.url)
        
        item = NewsItem()
        item['msource'] = response.url
        item['mtitle'] = response.css('.book-info h1:first-of-type').extract()
        item['mcontent'] = response.css('.book-info .intro').extract()
        item['mintro'] = response.css('.book-info .intro').extract()
        item['mpic'] = response.css('.book-img img:first-of-type').extract()
        item['mtags'] = response.css('.book-info .tag').extract()
        return item
    
# if __name__ == '__main__':
#     database = sqlite3.connect('urlRelations.db')
#     database.execute("CREATE TABLE IF NOT EXISTS UrlRelation(url text,parentUrl text,primary key(url,parentUrl))")
#     database.commit()
#     database.close()
#     database = sqlite3.connect('urlRelations.db')
#     url_relations = {'8' : ['1','2','1'], '9' : '2', '10' : '3', '11' : '1'}
#     for key, value in url_relations.items():
#         for listItem in value:
#             try:
#                 print((str(key), str(listItem)))
#                 database.execute("INSERT INTO UrlRelation(url,parentUrl) VALUES(?,?)", (str(key), str(listItem)))
#             except sqlite3.IntegrityError:
#                 print('error')
#                 pass
#     database.commit()
#     print('store relation commit')
#     database.close()
#     urls = ['a', 'a', 'b', 'b']
#     urls = list({}.fromkeys(urls).keys())
#     print(urls)
#     try:
#         file = open("urlRelations.json", 'r')
#         url_relations_recent = file.read()
#         url_relations_recent = {} if url_relations_recent.strip()=='' else json.loads(url_relations_recent)
#             
#         print(url_relations_recent.items())
#         for url_relation in url_relations_recent.items():
#             print(url_relation)
#     except IOError:
#         pass
#     finally:
#         file.close()
    