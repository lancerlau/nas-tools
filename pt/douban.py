import datetime
import random
from time import sleep

import requests
from bs4 import BeautifulSoup

import log
from config import get_config
from rmt.metainfo import MetaInfo
from utils.http_utils import RequestUtils
from utils.types import MediaType


class DouBan:
    req = None
    __default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"}
    __users = []
    __cookie = None
    __days = 0
    __types = []
    __headers = None

    def __init__(self):
        config = get_config()
        if config.get('douban'):
            # 用户列表
            users = config['douban'].get('users')
            if users:
                if not isinstance(users, list):
                    users = [users]
                self.__users = users
            # 时间范围
            self.__days = config['douban'].get('days')
            # 类型
            types = config['douban'].get('types')
            if types:
                self.__types = types.split(',')
            # headers
            user_agent = config['douban'].get('user_agent')
            if not user_agent:
                self.__headers = self.__default_headers
            else:
                self.__headers = {"User-Agent": f"{user_agent}"}

            self.req = RequestUtils(request_interval_mode=True)
            # Cookie
            cookie = config['douban'].get('cookie')
            if not cookie:
                try:
                    if self.req:
                        res = self.req.get_res("https://www.douban.com/", headers=self.__headers)
                        if res:
                            cookies = res.cookies
                            cookie = requests.utils.dict_from_cookiejar(cookies)
                            self.__cookie = cookie
                except Exception as err:
                    log.warn(f"【DOUBAN】获取cookie失败:{format(err)}")

    def get_all_douban_movies(self):
        movie_list = []
        start_number = 0
        # 每一个用户
        for user in self.__users:
            if not user:
                continue
            # 每一个类型
            user_succnum = 0
            for mtype in self.__types:
                if not mtype:
                    continue
                log.info(f"【DOUBAN】开始获取 {user} 的 {mtype} 数据...")
                err_url = []
                user_type_succnum = 0
                # 每一页
                while True:
                    page_number = int(start_number / 15 + 1)
                    # 每一页的文本
                    log.info(f"【DOUBAN】开始解析第 {page_number} 页数据...")
                    soup = self.__get_html_soup(user_id=user, media_status=mtype, start_number=start_number)
                    # 获取全部url
                    url_dict = self.__get_url_list(soup, self.__days)
                    url_list = url_dict["url_list"]
                    url_num = len(url_list)
                    log.info(f"【DOUBAN】第 {page_number} 页有 {url_num} 个媒体")
                    monitoring_info = url_dict["monitoring_info"]
                    log.info(f"【DOUBAN】本页监控日期内的数据为：{monitoring_info[0]}")
                    log.info(f"【DOUBAN】是否继续访问下一页：{monitoring_info[1]}")
                    sucess_urlnum = 0
                    url_count = 0
                    for url in url_list:
                        if url_count == monitoring_info[0] and not monitoring_info[1]:
                            log.info("【DOUBAN】其他媒体不在监控时间内，结束导入")
                            break
                        else:
                            url_count += 1
                        # 随机休眠
                        time_number = round(random.uniform(1, 5), 1)
                        log.info(f"【DOUBAN】解析媒体 {url_count} 随机休眠：{time_number}s")
                        sleep(time_number)
                        # 每一个条目的内容
                        media_soup = self.__get_html_soup(user_id=user, url=url, media_status=mtype)
                        if not media_soup:
                            log.warn(f"【DOUBAN】访问该页面出现问题，媒体链接：{url}")
                            err_url.append(url)
                        else:
                            movie_dict = self.__get_movie_dict(media_soup)
                            if movie_dict:
                                # 加入数组
                                if movie_dict not in movie_list:
                                    log.info(f"【DOUBAN】解析到媒体：%s" % movie_dict.get_name())
                                    movie_list.append(movie_dict)
                                    sucess_urlnum += 1
                                    user_type_succnum += 1
                                    user_succnum += 1
                    if monitoring_info[1] is False:
                        break
                    if url_num > 14:
                        start_number += 15
                    else:
                        break
                    log.info(f"【DOUBAN】第 {page_number} 页解析完成，共获取到 {sucess_urlnum} 个媒体")
                log.info(f"【DOUBAN】用户 {user} 的 {mtype} 解析完成，共获取到 {user_type_succnum} 个媒体")
            log.info(f"【DOUBAN】用户 {user} 解析完成，共获取到 {user_succnum} 个媒体")
        log.info(f"【DOUBAN】所有用户解析完成，共获取到 {len(movie_list)} 个媒体")

        return movie_list

    @staticmethod
    def __get_url_list(soup, monitoring_day=0):
        """
        解析个人wish/do/collect内容的每个url
        :return: { url_list: [url数组], monitoring_info: [符合日期的个数,是否继续]}
        """
        url_list = []
        continue_request = True
        monitoring_info = [0, continue_request]
        url_dict = {}
        try:
            info = soup.select('.nbg')
            for url in info:
                url_list.append(url.get('href'))
            if monitoring_day != 0:
                mark_date = soup.select('span.date')
                # 处理所有标记时间
                num = 0
                mark_date_dict = {}
                while num < len(mark_date):
                    mark_date_dict[num] = list(mark_date[num].strings)
                    mark_date_dict[num] = ''.join([i.split("\n", 1)[0] for i in mark_date_dict[num] if i.strip() != ''])
                    num += 1
                # 获取当天时间
                today = datetime.datetime.now()
                # 判断 标记时间
                # 符合监控日期内媒体个数计数
                count_num = 0
                for key in mark_date_dict:
                    mark_date_i = datetime.datetime.strptime(mark_date_dict.get(key), '%Y-%m-%d')
                    interval = today - mark_date_i
                    if interval.days < monitoring_day:
                        count_num += 1
                    else:
                        break
            else:
                # 如果没有监控日期，与媒体个数相同即可
                count_num = len(url_list)
            # 如果该页媒体为15，且监控没有限制或者都在监控日期内，则继续获取下一页内容
            if len(url_list) == 15 and count_num == len(url_list):
                continue_request = True
            else:
                continue_request = False

            monitoring_info[0] = count_num
            monitoring_info[1] = continue_request
            url_dict["url_list"] = url_list
            url_dict["monitoring_info"] = monitoring_info
            return url_dict
        except Exception as err:
            log.warn(f"【DOUBAN】解析失败：{err}")
            return url_dict

    def __get_html_soup(self, user_id, url=None, media_status="wish", start_number=0):
        """
        获取链接的html文档
        :param user_id: 用户id(如果url选择第二种则为空）
        :param media_status: 状态（wish/do/collect），同上
        :param start_number: url为空时，该参数必填
        :return: html的text格式
        """
        if not user_id:
            return None
        if not url:
            url = f"https://movie.douban.com/people/{user_id}/{media_status}?start={start_number}&sort=time&rating=all&filter=all&mode=grid"
        try:
            res = self.req.get_res(url=url, headers=self.__headers, cookies=self.__cookie)
            if res.status_code == 200:
                res_text = res.text
                if res_text.find('有异常请求从你的 IP 发出') != -1:
                    log.warn("【DOUBAN】被豆瓣识别到抓取行为了，请更换 IP 后才能使用")
                    return None
                return BeautifulSoup(res_text, 'html.parser')
            elif res.status_code == 404:
                log.warn(f"【DOUBAN】该页面不存在！{url}")
                return None
        except Exception as err:
            log.error(f"【RUN】获取{url}页面失败:{format(err)}")
            return None

    def __get_movie_dict(self, soup):
        # 标签名不加任何修饰，类名前加点，id名前加#
        try:
            info = soup.select('#info')
            infos = list(info[0].strings)
            infos = [i.strip() for i in infos if i.strip() != '']
            # 影视名称
            title = soup.select('#wrapper > div > h1')
            titles = list(title[0].strings)
            titles = [i.strip() for i in titles if i.strip() != '']
            douban_title = ''.join(titles)
            # 这里解析一下，拿到标题和年份、还有标题中的季
            meta_info = MetaInfo(douban_title)
            # 分类 电影和电视剧
            if '集数:' in infos or '单集片长:' in infos:
                meta_info.type = MediaType.TV
            else:
                meta_info.type = MediaType.MOVIE
            # 评分 评价数
            meta_info.vote_average = float(self.__get_media_rating_list(soup)[0])
            # 图片网址
            meta_info.poster_path = soup.select("#mainpic > a > img")[0].attrs['src']
        except Exception as e:
            log.error("【DOUBAN】解析出错：%s" % str(e))
            return None
        return meta_info

    @staticmethod
    def __get_single_info_list(infos_list, str_key):
        """
        获取豆瓣信息， 针对豆瓣:和关键字在一起的
        :param infos_list: 字符串列表
        :param str_key: 字符串字典关键字
        :return: 对应key值信息的列表
        """
        str_list = []
        try:
            if str_key in infos_list:
                data_list_tmp = infos_list[infos_list.index(str_key) + 1]
                data_list_tmp = data_list_tmp.split('/')
                for i in data_list_tmp:
                    str_list.append(i.strip(' '))
            else:
                log.warn(f"【DOUBAN】未解析到<{str_key}>信息")
            return str_list
        except Exception as err:
            log.error(f"【DOUBAN】未解析到<{str_key}>信息:{err}")
            return str_list

    @staticmethod
    def __multiple_infos_parser(str_dict, str_key, next_number):
        str_list = []
        try:
            first_index = str_dict.index(str_key) + next_number
            str_list.append(str_dict[first_index])
            next_index = first_index
            while True:
                if str_dict[next_index + 1] == '/':
                    next_index += 2
                    str_list.append(str_dict[next_index])
                else:
                    break
            return str_list
        except Exception as err:
            log.warn(f"【DOUBAN】未解析到{str_key}数据：{err}")
            return str_list

    @staticmethod
    def __get_media_rating_list(soup):
        rating_list = ['0', '0']
        try:
            rating_info = soup.select("#interest_sectl > div > div.rating_self.clearfix")
            rating_infos = list(rating_info[0].strings)
            rating_infos = [i.strip() for i in rating_infos if i.strip() != '']
            if len(rating_infos) > 2:
                rating_list = rating_infos
            else:
                rating_list[0] = 0.0
                rating_list[1] = 0
            return rating_list
        except Exception as err:
            log.warn(f"【DOUBAN】未解析到评价数据：{err}")
            return rating_list

    @staticmethod
    def __get_media_related_infos(info):
        try:
            if info:
                related_infos = list(info[0].strings)
                related_infos = [i.strip() for i in related_infos if i.strip() != '']
                related_infos = "\n".join(related_infos)
                return related_infos
            else:
                return "暂无。"
        except Exception as err:
            log.warn(f"【DOUBAN】未解析到简介：{err}")
            return "暂无..."


if __name__ == "__main__":
    print(DouBan().get_all_douban_movies())
