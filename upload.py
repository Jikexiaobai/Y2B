import json
import os
import re
import subprocess
import time
import requests
import xmltodict
import yaml
import argparse
import logging
import sys

# 定义常量
UPLOAD_SLEEP_SECOND = 60 * 2  # 上传间隔时间，2分钟
UPLOADED_VIDEO_FILE = "uploaded_video.json"  # 已上传视频信息文件名
CONFIG_FILE = "config.json"  # 配置文件名
COOKIE_FILE = "cookie.json"  # Cookie文件名
VERIFY = os.environ.get("verify", "1") == "1"  # SSL验证
PROXY = {
    "https": os.environ.get("https_proxy", None)  # HTTPS代理
}



# 通过Gist ID获取已上传数据（已上传视频信息、配置信息和cookie信息）。
def get_gist(_gid, token):
    """通过 gist id 获取已上传数据"""
    rsp = requests.get(
        "https://api.github.com/gists/" + _gid,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
        },
        verify=VERIFY,
    )
    if rsp.status_code == 404:
        raise Exception("gist id 错误")
    if rsp.status_code == 403 or rsp.status_code == 401:
        raise Exception("github TOKEN 错误")
    _data = rsp.json()
    uploaded_file = _data.get("files", {}).get(
        UPLOADED_VIDEO_FILE, {}).get("content", "{}")
    c = json.loads(_data["files"][CONFIG_FILE]["content"])
    t = json.loads(_data["files"][COOKIE_FILE]["content"])
    try:
        u = json.loads(uploaded_file)
        return c, t, u
    except Exception as e:
        logging.error(f"gist 格式错误，重新初始化:{e}")
    return c, t, {}

# 将数据写入到指定的文件中，并更新Gist。
def update_gist(_gid, token, file, data):
    rsp = requests.post(
        "https://api.github.com/gists/" + _gid,
        json={
            "description": "y2b暂存数据",
            "files": {
                file: {
                    "content": json.dumps(data, indent="  ", ensure_ascii=False)
                },
            }
        },
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
        },
        verify=VERIFY,
    )
    if rsp.status_code == 404:
        raise Exception("gist id 错误")
    if rsp.status_code == 422:
        raise Exception("github TOKEN 错误")

# 获取指定文件的大小。
def get_file_size(filename):
    sz = os.path.getsize(filename)
    return int(sz/1024/1024)

# 获取指定YouTube频道的视频列表。
def get_video_list(channel_id: str):
    res = requests.get(
        "https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id).text
    res = xmltodict.parse(res)
    ret = []
    for elem in res.get("feed", {}).get("entry", []):
        ret.append({
            "vid": elem.get("yt:videoId"),
            "title": elem.get("title"),
            "origin": "https://www.youtube.com/watch?v=" + elem["yt:videoId"],
            "cover_url": elem["media:group"]["media:thumbnail"]["@url"],
            # "desc": elem["media:group"]["media:description"],
        })
    return ret

# 从视频列表中筛选出未上传过的视频。
def select_not_uploaded(video_list: list, _uploaded: dict):
    ret = []
    for i in video_list:
        if _uploaded.get(i["detail"]["vid"]) is not None:
            logging.debug(f'vid:{i["detail"]["vid"]} 已被上传')
            continue
        logging.debug(f'vid:{i["detail"]["vid"]} 待上传')
        ret.append(i)
    return ret

# 从视频列表中选取每个频道的前n个未上传视频
def select_top_n_not_uploaded(video_list: list, _uploaded: dict):
    """
    从视频列表中选出未上传的前n个视频，按照频道ID分组。

    参数:
    video_list: list，包含视频信息的列表，每个元素是(视频ID, 视频详情)的元组。
    _uploaded: dict，记录已上传视频的字典，键为视频ID，值为上传状态（非None表示已上传）。

    返回值:
    list，包含每个频道未上传的前n个视频详情的列表。
    """
    channel_video_num = 3 # 频道中待上传的视频数量
    ret = {}
    # 遍历视频列表，筛选未上传的视频并按频道ID分组
    for vid, detail in video_list:
        # 检查视频是否已上传
        if _uploaded.get(vid) is not None:
            logging.debug(f'veid:{vid} 已被上传')
            continue
        logging.debug(f'veid:{vid} 待上传')
        # 将detail转换为字典类型
        logging.debug(f"Detail content: {detail}")
        #detail_dict = detail if isinstance(detail, dict) else json.loads(detail)
        # 按频道ID分组，并确保每个频道未上传的视频不超过n个
        if detail_dict["channel_id"] not in ret:
            ret[detail_dict["channel_id"]] = []
        if len(ret[detail_dict["channel_id"]]) < channel_video_num:
            ret[detail_dict["channel_id"]].append(detail)
        else:
            logging.debug(f'频道{detail_dict["channel_id"]}已满{channel_video_num}个待上传视频')
        # 返回每个频道未上传的前n个视频详情
    return ret.values()


# 获取所有需要上传的视频信息。
def get_all_video(_config):
    ret = []
    for i in _config:
        res = get_video_list(i["channel_id"])
        for j in res:
            ret.append({
                "detail": j,
                "config": i
            })
    return ret

# 下载指定URL的视频，并以指定格式保存。
def download_video(url, out, format):
    try:
        msg = subprocess.check_output(
            ["yt-dlp", url, "-f", format, "-o", out], stderr=subprocess.STDOUT)
        logging.debug(msg[-512:])
        logging.info(f"视频下载完毕，大小：{get_file_size(out)} MB")
        return True
    except subprocess.CalledProcessError as e:
        out = e.output.decode("utf8")
        if "This live event will begin in" in out:
            logging.info("直播预告，跳过")
            return False
        if "Requested format is not available" in out:
            logging.debug("视频无此类型：" + format)
            return False
        if "This video requires payment to watch" in out:
            logging.info("付费视频，跳过")
            return False
        logging.error("未知错误:" + out)
        raise e

# 下载指定URL的封面图片，并保存到指定路径。
def download_cover(url, out):
    res = requests.get(url, verify=VERIFY).content
    with open(out, "wb") as tmp:
        tmp.write(res)


def filter_string(text):
    """
    过滤字符串中除了中文、英文、数字 以外的字符，并且去掉韩文字符 'ㅣ'和韩文，保留符号 '&'
    """
    pattern = r'[^\w\s\u4e00-\u9fa5&]+|[ㅣ\uac00-\ud7af]+'
    return re.sub(pattern, '', text)

# 使用biliup工具上传指定视频文件到B站。
def upload_video(video_file, cover_file, _config, detail):
    title_y = detail['title']
    title = filter_string(title_y)
    if len(title) > 75:
        title = title[:75]
    yml = {
        "line": "kodo",
        "limit": 3,
        "streamers": {
            video_file: {
                "copyright": 2,
                "source": detail['origin'],
                "tid": _config['tid'],  # 投稿分区
                "cover": cover_file,  # 视频封面
                "title": "【搬运】" + title, # 稿件标题
                "desc_format_id": 0,
                "desc": "由董岩松博客(dongyansong.com)自动搬运\nLaunchpad交流群：780893886 （禁止任何阴阳怪气、怼人等任何带有负能量的蠕虫网友入群）\n工程可以访问原视频看简介有没有(或加群问一下有没有)\nLaunchpad论坛：https://9b7.cn\n关于Launchpad搬运系列：使用董岩松博客编写的《YTB_to_bili》开源项目自动运行。\n该项目经过半年长期运行，确保并不会对B站造成任何无用的垃圾数据，请B站与各用户知悉。\n原视频：" + detail["origin"],
                "dolby": 0,  # 杜比音效
                "dynamic": "",
                "subtitle": {
                    "open": 0,
                    "lan": ""
                },
                "tag": _config['tags'],
                "open_subtitle": False,
            }
        }
    }
    with open("config.yaml", "w", encoding="utf8") as tmp:
        t = yaml.dump(yml, Dumper=yaml.Dumper)
        logging.debug(f"biliup 业务配置：{t}")
        tmp.write(t)
    p = subprocess.Popen(
        ["biliup", "upload", "-c", "config.yaml"],
        stdout=subprocess.PIPE,
    )
    p.wait()
    if p.returncode != 0:
        error_ret = json.loads(p.stdout.read())
        pushplus_data = {
        "token": "74dadec01cd345e5bb01204bef88fb97",
        "title": "搬运失败《" + detail['title'] + "》",
        "content": "稿件《" + detail['title'] + "》" + "\n报错信息为 " + ret["data"] + "\n原视频地址 " + detail["origin"]
        }
        res = requests.post("http://www.pushplus.plus/send", data=pushplus_data, proxies=PROXY)
        raise Exception(p.stdout.read())
    buf = p.stdout.read().splitlines(keepends=False)
    if len(buf) < 2:
        raise Exception(buf)
    try:
        data = buf[-2]
        data = data.decode()
        data = re.findall("({.*})", data)[0]
    except Exception as e:
        logging.error(f"输出结果错误:{buf}")
        raise e
    logging.debug(f'上传完成，返回：{data}')
    ret = json.loads(data)
    pushplus_data = {
        "token": "74dadec01cd345e5bb01204bef88fb97",
        "title": "搬运成功《" + detail['title'] + "》",
        "content": "稿件《" + detail['title'] + "》" + "\nBV号：" + ret["data"]["bvid"] + "\n原视频地址 " + detail["origin"]
    }
    res = requests.post("http://www.pushplus.plus/send", data=pushplus_data, proxies=PROXY)
    return json.loads(data)

# 针对单个视频进行上传处理。
def process_one(detail, config):
    logging.info(f'开始：{detail["vid"]}')
    format = ["webm", "flv", "mp4"]
    v_ext = None
    for ext in format:
        if download_video(detail["origin"], detail["vid"] + f".{ext}", f"{ext}"):
            v_ext = ext
            logging.info(f"使用格式：{ext}")
            break
    if v_ext is None:
        logging.error("无合适格式")
        return
    download_cover(detail["cover_url"], detail["vid"] + ".jpg")
    ret = upload_video(detail["vid"] + f".{v_ext}",
                       detail["vid"] + ".jpg", config, detail)
    os.remove(detail["vid"] + f".{v_ext}")
    os.remove(detail["vid"] + ".jpg")
    return ret

# 执行整个上传流程。
def upload_process(gist_id, token):
    """
    该函数用于将 YouTube 频道中未上传的视频搬运到B站。
    :param gist_id: str, Gist ID.
    :param token: str, GitHub Token.
    :return: None
    """
    config, cookie, uploaded = get_gist(gist_id, token)
    with open("cookies.json", "w", encoding="utf8") as tmp:
        tmp.write(json.dumps(cookie))
    all_videos = get_all_video(config)
    need_to_process = select_top_n_not_uploaded(all_videos, uploaded)  # 使用新函数
    for video_group in need_to_process:
        for detail in video_group:
            ret = process_one(detail, config)
            if ret is None:
                continue
            detail["ret"] = ret
            uploaded[detail["vid"]] = detail
            update_gist(gist_id, token, UPLOADED_VIDEO_FILE, uploaded)
            logging.info(
                f'上传完成,稿件vid:{detail["vid"]},aid:{ret["data"]["aid"]},Bvid:{ret["data"]["bvid"]}')
            logging.debug(f"防验证码，暂停 {UPLOAD_SLEEP_SECOND} 秒")
            time.sleep(UPLOAD_SLEEP_SECOND)
    os.system("biliup renew 2>&1 > /dev/null")
    with open("cookies.json", encoding="utf8") as tmp:
        data = tmp.read()
        update_gist(gist_id, token, COOKIE_FILE, json.loads(data))
    os.remove("cookies.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("token", help="github api token", type=str)
    parser.add_argument("gistId", help="gist id", type=str)
    parser.add_argument("--logLevel", help="log level, default is info",
                        default="INFO", type=str, required=False)
    args = parser.parse_args()
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.getLevelName(args.logLevel),
        format='%(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(levelname)s: %(message)s',
        datefmt="%H:%M:%S",
    )
    upload_process(args.gistId, args.token)
