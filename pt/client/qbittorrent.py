import os

import qbittorrentapi
import urllib3
import log
from config import get_config

# 全局设置
from rmt.filetransfer import FileTransfer
from utils.types import DownloaderType, MediaType

urllib3.disable_warnings()


class Qbittorrent:
    __qbhost = None
    __qbport = None
    __qbusername = None
    __qbpassword = None
    __tv_save_path = None
    __tv_save_containerpath = None
    __movie_save_path = None
    __movie_save_containerpath = None
    qbc = None
    filetransfer = None

    def __init__(self):
        self.filetransfer = FileTransfer()
        config = get_config()
        if config.get('qbittorrent'):
            self.__qbhost = config['qbittorrent'].get('qbhost')
            self.__qbport = config['qbittorrent'].get('qbport')
            self.__qbusername = config['qbittorrent'].get('qbusername')
            self.__qbpassword = config['qbittorrent'].get('qbpassword')
            # 解释下载目录
            save_path = config['qbittorrent'].get('save_path')
            if save_path:
                if isinstance(save_path, str):
                    self.__tv_save_path = save_path
                    self.__movie_save_path = save_path
                else:
                    self.__tv_save_path = save_path.get('tv')
                    self.__movie_save_path = save_path.get('movie')
            save_containerpath = config['qbittorrent'].get('save_containerpath')
            if save_containerpath:
                if isinstance(save_containerpath, str):
                    self.__tv_save_containerpath = save_containerpath
                    self.__movie_save_containerpath = save_containerpath
                else:
                    self.__tv_save_containerpath = save_containerpath.get('tv')
                    self.__movie_save_containerpath = save_containerpath.get('movie')
            if self.__qbhost and self.__qbport:
                self.qbc = self.__login_qbittorrent()

    # 连接qbittorrent
    def __login_qbittorrent(self):
        try:
            # 登录
            qbt = qbittorrentapi.Client(host=self.__qbhost,
                                        port=self.__qbport,
                                        username=self.__qbusername,
                                        password=self.__qbpassword,
                                        VERIFY_WEBUI_CERTIFICATE=False)
            return qbt
        except Exception as err:
            log.error("【QB】qBittorrent连接出错：%s" % str(err))
            return None

    # 读取所有种子信息
    def get_torrents(self, ids=None, status=None):
        # 读取qBittorrent列表
        if not self.qbc:
            return []
        self.qbc.auth_log_in()
        torrents = self.qbc.torrents_info(torrent_hashes=ids, status_filter=status)
        self.qbc.auth_log_out()
        return torrents

    # 迁移完成后设置种子状态
    def set_torrents_status(self, ids):
        if not self.qbc:
            return
        self.qbc.auth_log_in()
        # 打标签
        self.qbc.torrents_add_tags(tags="已整理", torrent_hashes=ids)
        # 超级做种
        self.qbc.torrents_set_force_start(enable=True, torrent_hashes=ids)
        log.info("【QB】设置qBittorrent种类状态成功！")
        self.qbc.auth_log_out()

    # 处理qbittorrent中的种子
    def transfer_task(self):
        # 处理所有任务
        log.info("【QB】开始转移PT下载文件...")
        torrents = self.get_torrents()
        trans_torrents = []
        for torrent in torrents:
            log.debug("【QB】" + torrent.get('name') + "：" + torrent.get('state'))
            if torrent.get('state') == "uploading" or torrent.get('state') == "stalledUP":
                true_path = torrent.get('content_path', os.path.join(torrent.get('save_path'), torrent.get('name')))
                if not true_path:
                    continue
                if self.__tv_save_containerpath:
                    true_path = true_path.replace(str(self.__tv_save_path), str(self.__tv_save_containerpath))
                if self.__movie_save_containerpath:
                    true_path = true_path.replace(str(self.__movie_save_path), str(self.__movie_save_containerpath))
                done_flag = self.filetransfer.transfer_media(in_from=DownloaderType.QB, in_path=true_path)
                if done_flag:
                    self.set_torrents_status(torrent.get('hash'))
                    trans_torrents.append(torrent.name)
                else:
                    log.error("【QB】%s 转移失败！" % torrent.get('name'))
        log.info("【QB】PT下载文件转移结束！")
        return trans_torrents

    # 做种清理
    def remove_torrents(self, seeding_time):
        log.info("【PT】开始执行qBittorrent做种清理...")
        torrents = self.get_torrents()
        for torrent in torrents:
            # 只有标记为强制上传的才会清理（经过RMT处理的都是强制上传状态）
            if torrent.get('state') == "forcedUP":
                if int(torrent.get('seeding_time')) > int(seeding_time):
                    log.info("【PT】" + torrent.get('name') + "做种时间：" + str(torrent.get('seeding_time')) +
                             "（秒），已达清理条件，进行清理...")
                    # 同步删除文件
                    self.delete_torrents(delete_file=True, ids=torrent.get('hash'))
        log.info("【PT】qBittorrent做种清理完成！")

    # 添加qbittorrent任务
    def add_torrent(self, turl, mtype):
        if not self.qbc:
            return False
        self.qbc.auth_log_in()
        if mtype == MediaType.TV:
            qbc_ret = self.qbc.torrents_add(urls=turl, save_path=self.__tv_save_path)
        else:
            qbc_ret = self.qbc.torrents_add(urls=turl, save_path=self.__movie_save_path)
        self.qbc.auth_log_out()
        return qbc_ret

    # 下载控制：开始
    def start_torrents(self, ids):
        if not self.qbc:
            return False
        return self.qbc.torrents_resume(torrent_hashes=ids)

    # 下载控制：停止
    def stop_torrents(self, ids):
        if not self.qbc:
            return False
        return self.qbc.torrents_pause(torrent_hashes=ids)

    # 删除种子
    def delete_torrents(self, delete_file, ids):
        if not self.qbc:
            return False
        self.qbc.auth_log_in()
        ret = self.qbc.torrents_delete(delete_files=delete_file, torrent_hashes=ids)
        self.qbc.auth_log_out()
        return ret
