#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time   : 2026/7/3 15:27
@Author : yange19940310@gmail.com
@File   : oss_service.py
"""

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from injector import inject
import alibabacloud_oss_v2 as oss
from sympy.physics.mechanics import body
from werkzeug.datastructures import FileStorage

from internal.entity.upload_file_entity import ALLOWED_IMAGE_EXTENSION, ALLOWED_DOCUMENT_EXTENSION
from internal.exception import FailException
from internal.model import UploadFile, Account
from .upload_file_service import UploadFileService


@inject
@dataclass
class OssService:
    """腾讯云cos对象存储服务"""
    upload_file_service: UploadFileService

    def upload_file(self, account:Account, file: FileStorage, only_image: bool = False) -> UploadFile:
        """上传文件到腾讯云cos对象存储，上传后返回文件的信息"""
        account_id = account.id

        # 1.提取文件扩展名并检测是否可以上传
        filename = file.filename
        extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
        if extension.lower() not in (ALLOWED_IMAGE_EXTENSION + ALLOWED_DOCUMENT_EXTENSION):
            raise FailException(f"该.{extension}扩展的文件不允许上传")
        elif only_image and extension not in ALLOWED_IMAGE_EXTENSION:
            raise FailException(f"该.{extension}扩展的文件不支持上传，请上传正确的图片")

        # 2.获取客户端+存储桶名字
        client = self._get_client()
        bucket = self._get_bucket()

        # 3.生成一个随机的名字
        random_filename = str(uuid.uuid4()) + "." + extension
        now = datetime.now()
        upload_filename = f"{now.year}/{now.month:02d}/{now.day:02d}/{random_filename}"

        # 4.流式读取上传的数据并将其上传到cos中
        file_content = file.stream.read()

        try:
            # 5.将数据上传到cos存储桶中
            client.put_object(oss.PutObjectRequest(
                bucket=bucket,
                key=upload_filename,
                body=file_content,
            ))
        except Exception as e:
            print('error', e)
            raise FailException("上传文件失败，请稍后重试")

        # 6.创建upload_file记录
        return self.upload_file_service.create_upload_file(
            account_id=account_id,
            name=filename,
            key=upload_filename,
            size=len(file_content),
            extension=extension,
            mime_type=file.mimetype,
            hash=hashlib.sha3_256(file_content).hexdigest(),
        )

    @classmethod
    def upload_bytes(
            cls,
            file_content: bytes,
            extension: str = "png",
            prefix: str = "generated-images",
    ) -> str:
        """将内存中的文件直接上传到 OSS，并返回公网访问地址。"""
        if not file_content:
            raise FailException("上传文件内容不能为空")
        safe_extension = (extension or "png").lower().lstrip(".")
        if safe_extension == "jpeg":
            safe_extension = "jpg"
        if safe_extension not in ALLOWED_IMAGE_EXTENSION:
            raise FailException(f"该.{safe_extension}扩展的文件不支持上传")

        now = datetime.now()
        object_key = (
            f"{prefix.strip('/')}/{now.year}/{now.month:02d}/{now.day:02d}/"
            f"{uuid.uuid4()}.{safe_extension}"
        )
        try:
            cls._get_client().put_object(oss.PutObjectRequest(
                bucket=cls._get_bucket(),
                key=object_key,
                body=file_content,
            ))
        except Exception as exc:
            raise FailException("上传文件失败，请稍后重试") from exc
        return cls.get_file_url(object_key)
    def download_file(self, key: str, file_path:str):
        """下载oos云端的文件到本地的指定路径"""
        client = self._get_client()
        bucket = self._get_bucket()

        result = client.get_object(oss.GetObjectRequest(bucket=bucket, key=key))

        with result.body as body_stream:
            data = body_stream.read()
            # 写入文件
            with open(file_path, 'wb') as f:
                f.write(data)


    @classmethod
    def get_file_url(cls, key: str) -> str:
        """根据传递的OSS云端key获取图片的实际URL地址"""
        cos_domain = os.getenv("OSS_DOMAIN")

        return f"{cos_domain}/{key}"

    @classmethod
    def _get_client(cls) -> oss.Client:
        """获取OSS对象存储客户端"""
        credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=os.getenv("OSS_ACCESS_KEY_ID"),
            access_key_secret=os.getenv("OSS_ACCESS_KEY_SECRET"),
        )
        # 加载SDK的默认配置，并设置凭证提供者
        cfg = oss.config.load_default()
        cfg.credentials_provider = credentials_provider
        # 填写Bucket所在地域
        cfg.region = 'cn-chengdu'

        # 使用配置好的信息创建OSS客户端
        client = oss.Client(cfg)
        return client

    @classmethod
    def _get_bucket(cls) -> str:
        """获取存储桶的名字"""
        return os.getenv("OSS_BUCKET")