# Y2B

把Youtube上的视频搬运到哔哩哔哩

交流QQ群：**849883545**

## 食用方法

### 初始化

1. 先执行`pip install -r requirements.txt`,然后再执行`python init.py`
2. 在conf文件夹,`setting.yaml`,在里面填写b站账号密码,再填写`GoogleApi`的密钥
3. `channel.yaml`是指定搬运的`Youtube`频道
4. 需要安装aria2c，并开启jsonrpc

### 运行

完成初始化后，直接`python main.py`就好了

### 注释

视频搬运分为两种方式，一种是分P，一种是不分P

- 分P就是将多个YouTube视频全部投递到一个b站视频的不同分P里，这种方式必须提前手动投递一个视频，然后填写BV号
- 不分P就是一个视频对应b站的一个BV，这种方式要填写一些额外的字段
- 所有设置以`setting_ex.yaml`的注释为准，不懂或有bug可以发issue或进QQ群**849883545**

## 软件依赖

- python >= 3.6
- aria2
- ffmpeg

## aria2c 参考配置

[aria.conf](./conf/aria.conf)

## 更新记录

- 2020.05.04
  - 增加定时任务
- 2020.05.03
  - 迁移配置文件为yaml
  - 修复封面丢失的问题
  - 修复字幕投递
- 2020.05.02
  - 增加自定义选项
  - 新增1080P
- 2020.05.01
  - 修复一些奇奇怪怪的bug
- 2020.04.29
  - 出现编码性错误，把之前所有的提交记录全部删除
