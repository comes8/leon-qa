"""Optional legacy RSA helpers. Keys must be provided explicitly at runtime."""
import os

def _configured_key(name):
    value = os.environ.get(name, '')
    if not value:
        raise RuntimeError(f'{name} is not configured')
    return value

import base64

from Cryptodome import Random

from Cryptodome.Cipher import PKCS1_v1_5

from Cryptodome.PublicKey import RSA

def generate_secret_key():
    """
    公钥私钥生成
    :return:
    """
    random_generator = Random.new().read
    rsa = RSA.generate(2048, random_generator)
    private_key = rsa.exportKey()
    public_key = rsa.publickey().exportKey()
    return (private_key.decode('utf8'), public_key.decode('utf8'))

def encrypt_rsa_password(password):
    """
    密码加密
    :param password:
    :return:
    """
    try:
        public_key = RSA.import_key(_configured_key('LEON_QA_RSA_PUBLIC_KEY'))
        cipher = PKCS1_v1_5.new(public_key)
        text = cipher.encrypt(password.encode('utf8'))
        return base64.b64encode(text)
    except Exception as err:
        raise ValueError('RSA encryption failed; check configured key') from err

def decrypt_rsa_password(password):
    """
    密码解密
    :param password:
    :return:
    """
    try:
        private_key = RSA.import_key(_configured_key('LEON_QA_RSA_PRIVATE_KEY'))
        cipher = PKCS1_v1_5.new(private_key)
        text = cipher.decrypt(base64.b64decode(password), b'')
        return text.decode()
    except Exception as err:
        raise ValueError('RSA decryption failed; check configured key') from err
