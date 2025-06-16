# blog/management/commands/test_wasabi_connection.py
import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Test connection to Wasabi S3 storage using settings.py configurations.'

    def handle(self, *args, **options):
        try:
            # 获取settings中配置的Wasabi信息
            aws_access_key_id = settings.AWS_ACCESS_KEY_ID
            aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY
            aws_storage_bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            aws_s3_endpoint_url = settings.AWS_S3_ENDPOINT_URL
            aws_s3_region_name = getattr(settings, 'AWS_S3_REGION_NAME', None) # 确保获取区域名，如果没有则为None
            aws_s3_signature_version = getattr(settings, 'AWS_S3_SIGNATURE_VERSION', 's3v4')

            if not all([aws_access_key_id, aws_secret_access_key, aws_storage_bucket_name, aws_s3_endpoint_url]):
                raise CommandError("Wasabi S3 configuration is incomplete in settings.py. "
                                    "Please check AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL.")

            # 初始化boto3客户端
            self.stdout.write(self.style.NOTICE(f"尝试连接 Wasabi S3: {aws_s3_endpoint_url}"))
            self.stdout.write(self.style.NOTICE(f"使用存储桶: {aws_storage_bucket_name}"))

            s3_client = boto3.client(
                's3',
                endpoint_url=aws_s3_endpoint_url,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=aws_s3_region_name, # 如果未定义，boto3会自动处理
                config=boto3.session.Config(signature_version=aws_s3_signature_version)
            )

            # 尝试列出存储桶中的对象（文件）
            # 注意：如果存储桶是空的，这不会报错，但会返回空列表
            self.stdout.write(self.style.NOTICE("尝试列出存储桶中的前5个对象..."))
            response = s3_client.list_objects_v2(Bucket=aws_storage_bucket_name, MaxKeys=5)

            if 'Contents' in response:
                self.stdout.write(self.style.SUCCESS("成功列出存储桶对象："))
                for obj in response['Contents']:
                    self.stdout.write(self.style.SUCCESS(f"- {obj['Key']}"))
            else:
                self.stdout.write(self.style.WARNING("存储桶中没有对象，或无法获取对象列表。这可能是由于存储桶为空或权限问题导致。"))

            # 尝试上传一个小文件进行写入测试
            test_file_content = b"This is a test file for Wasabi connection."
            test_file_key = "test_connection.txt"
            self.stdout.write(self.style.NOTICE(f"尝试上传测试文件 '{test_file_key}' 到存储桶..."))
            s3_client.put_object(
                Bucket=aws_storage_bucket_name,
                Key=test_file_key,
                Body=test_file_content
            )
            self.stdout.write(self.style.SUCCESS(f"文件 '{test_file_key}' 上传成功！"))

            # 尝试删除测试文件
            self.stdout.write(self.style.NOTICE(f"尝试删除测试文件 '{test_file_key}'..."))
            s3_client.delete_object(
                Bucket=aws_storage_bucket_name,
                Key=test_file_key
            )
            self.stdout.write(self.style.SUCCESS(f"文件 '{test_file_key}' 删除成功！"))

            self.stdout.write(self.style.SUCCESS("\nWasabi S3 连接测试成功！凭证、Endpoint 和存储桶操作均正常。"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Wasabi S3 连接测试失败：{e}"))
            raise CommandError(f"Wasabi S3 连接测试失败：{e}")
