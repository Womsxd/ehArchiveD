import re
import os
import json
import time
import httpx
import logging
import datetime

# 设置日志输出格式
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S')
log = logging

# 设置httpx日志输出格式
httpx_log = logging.getLogger("httpx")
httpx_log.setLevel(logging.INFO)

# 设置下载目录
base_path = os.path.join(os.path.dirname(__file__), 'downloads')
if not os.path.exists(base_path):
    os.mkdir(base_path)

# 设置保存目录
save_path = os.path.join(base_path, datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
log.info('保存目录为：' + save_path)
if not os.path.exists(save_path):
    os.mkdir(save_path)
    log.info('创建目录：' + save_path)

# 定义一个正则表达式模式，该模式用于匹配e-hentai或ex-hentai画廊链接
# 此正则表达式中的核心逻辑：
# - 'https://(?:e-|ex)hentai.org/g/' 匹配e-hentai或ex-hentai画廊链接的基本URL部分
# - '(\d+)' 匹配并捕获整数形式的画廊ID
# - '(/[a-f0-9]+)' 匹配并捕获一组小写十六进制字符，作为画廊的唯一标识符（hash或token）
pattern_gallery_url = r'https://(?:e-|ex)hentai.org/g/(\d+)/([a-f0-9]+)'

# 定义URL匹配模式
# 模式描述：查找HTML中形如<document.location = "https://任意字符.hath.network/任意字符">的链接标签
# 其中，"任意字符"指除了双引号(")之外的任何字符，通过[^"]+表示
pattern_download = r'document.location = "(https://[^"]+\.hath\.network/[^"]+)"'

# 将上述模式编译为正则表达式对象
# 编译后的正则对象可以用于后续的字符串搜索和匹配操作
regexp_gallery_url = re.compile(pattern_gallery_url)
regexp_download = re.compile(pattern_download, re.DOTALL)

# 定义e-hentai的基地址
eHentai_base_url = 'https://e-hentai.org/'
eHentai_url_template = eHentai_base_url + 'g/{gid}/{token}/'
eHentai_get_download_url_template = eHentai_base_url + 'archiver.php?gid={gid}&token={token}&or={archiver_key}'

eHentai_get_archive_org_url_payload = {"dltype": "org", "dlcheck": "Download+Original+Archive"}
eHentai_get_archive_res_url_payload = {"dltype": "res", "dlcheck": "Download+Resample+Archive"}

http_timeout = 10
http_proxy = "http://127.0.0.1:10809"
http_cookie = ""

base_headers = {
    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 "
                  "Safari/537.36",
    'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
              "application/signed-exchange;v=b3;q=0.7",
    'origin': "https://e-hentai.org",
    'dnt': "1",
    'upgrade-insecure-requests': "1",
    'referer': "",
    'accept-language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    'sec-gpc': "1",
    'Cookie': http_cookie,
}


# 获取一个新的httpx客户端，并设置超时和代理
def get_client(**kwargs) -> httpx.Client:
    return httpx.Client(timeout=http_timeout, proxy=http_proxy, **kwargs)


def get_gallery_url(url: str) -> list:
    """获取画廊链接
    Args:
        url (str): 画廊链接
    Returns:
        list: 画廊的id和token
    """
    # 使用正则表达式对象匹配字符串
    # 如果匹配成功，返回匹配结果
    # 否则，返回None
    result = regexp_gallery_url.match(url)
    if result:
        try:
            return [result.group(1), result.group(2)]
        # 如果捕获的分组数量小于2，说明匹配失败
        except IndexError:
            log.error('Failed to get gallery url')
    return []


def urls_to_ids(urls: list) -> tuple:
    """将画廊链接转换为id和token
    Args:
        urls (list): 画廊链接列表
    Returns:
        tuple: 有效的画廊id和token列表, 无效的画廊链接列表
    """
    ids = []
    invalid_urls = []
    for url in urls:
        result = get_gallery_url(url)
        if not result:
            invalid_urls.append(url)
        else:
            ids.append(result)
    return ids, invalid_urls


def load_gallery_urls(urls_file: str) -> list:
    """加载画廊链接
    Args:
        urls_file (str): 画廊链接文件路径
    Returns:
        list: 画廊链接列表
    """
    with open(urls_file, 'r', encoding='utf-8') as f:
        urls = f.read().splitlines()
    return urls


def handle_invalid_urls(invalid_urls: list) -> None:
    """处理无效的画廊链接
    Args:
        invalid_urls (list): 无效的画廊链接列表
    """
    if invalid_urls:
        log.info('发现' + str(len(invalid_urls)) + '个无效的画廊链接')
        # 将无效的画廊链接写入文件
        with open(os.path.join(save_path, 'invalid_urls.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(invalid_urls))


def handle_invalid_gids_and_tokens(invalid_gids_and_tokens: list) -> None:
    """处理无效的gid和token 现在只会回写gid
    Args:
        invalid_gids_and_tokens (list): 无效的gid和token列表
    """
    if invalid_gids_and_tokens:
        log.info('发现' + str(len(invalid_gids_and_tokens)) + '个无效的gid和token')
        # 将无效的画廊链接写入文件
        # invalid_gid_and_token_urls
        with open(os.path.join(save_path, 'invalid_gid.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(invalid_gids_and_tokens))
            # for gid, token in invalid_gids_and_tokens:
            #    url = eHentai_url_template.format(gid=gid, token=token)
            #    f.write(url + '\n')


def get_archiver_info(ids: list) -> dict:
    """获取画廊的全部信息
    Args:
        ids (list): 画廊id和token列表
    Returns:
        dict: 对原来的json进行扩充后的json
    """
    url = eHentai_base_url + 'api.php'
    all_archiver_info = []
    invalid_gids = []
    with get_client() as client:
        log.info('正在获取画廊的archiver_key')
        for i in range(0, len(ids), 25):
            payload = {
                'method': 'gdata',
                'gidlist': ids[i:i + 25],
                'namespace': 1
            }
            response = client.post(url, json=payload)
            if response.status_code == 200:
                try:
                    result = response.json()
                    for item in result['gmetadata']:
                        if item.get('error', None):
                          log.error(f'{item["gid"]}: {item["error"]}')
                          invalid_gids.append(item['gid'])
                          continue
                        all_archiver_info.append(item)
                except json.decoder.JSONDecodeError:
                    log.error(f'Failed to parse JSON response: {response.text}')
            else:
                log.error(f'Failed to get archiver_key. Status code: {response.status_code}')
        time.sleep(4)
    handle_invalid_gids_and_tokens(invalid_gids)
    return {"gmetadata": all_archiver_info}


def get_download_urls(archiver_info: dict) -> dict:
    """获取全部的下载地址
    Args:
        archiver_info (dict): 画廊的全部信息
    Returns:
        dict: 画廊的全部信息
    """

    with get_client() as client:
        log.info('正在获取下载地址')
        headers = base_headers.copy()
        for item in archiver_info['gmetadata']:
            url = eHentai_get_download_url_template.format(gid=item['gid'], token=item['token'],
                                                           archiver_key=item['archiver_key'])
            headers['referer'] = url
            response = client.post(url, headers=headers, data=eHentai_get_archive_org_url_payload)
            if response.status_code == 200:
                try:
                    item['download_url'] = regexp_download.search(response.text).group(1)
                    item['download_url'] += "?start=1"
                    # 补充归档下载的文件链接
                except IndexError:
                    log.error(f'Failed to get download url: {item["gid"]}')
            else:
                log.error(f'Failed to get download url: {item["gid"]}')
            time.sleep(2)
    return archiver_info


def save_gallery_info(archiver_info: dict) -> None:
    """保存画廊信息
    Args:
        archiver_info (dict): 画廊的全部信息
    """
    with open(os.path.join(save_path, 'gallery_info.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(archiver_info, ensure_ascii=False, indent=4))


def save_download_urls(archiver_info: dict) -> None:
    """保存全部的下载地址
    Args:
        archiver_info (dict): 画廊的全部信息
    """
    with open(os.path.join(save_path, 'download_urls.txt'), 'w', encoding='utf-8') as f:
        for item in archiver_info['gmetadata']:
            f.write(item['download_url'] + '\n')


def main():
    file_name = input("请输入url文件路径: ")
    load_urls = load_gallery_urls(file_name)
    ids, invalid_urls = urls_to_ids(load_urls)
    handle_invalid_urls(invalid_urls)
    if not ids:
        log.info('未发现有效的画廊链接')
        exit(0)
    all_archiver_info = get_archiver_info(ids)
    all_archiver_info = get_download_urls(all_archiver_info)
    save_gallery_info(all_archiver_info)
    save_download_urls(all_archiver_info)


if __name__ == '__main__':
    main()
