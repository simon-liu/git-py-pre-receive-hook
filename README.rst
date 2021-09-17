在 Git 服务器端使用 black+flake8 命令检查 Python 编码规范
========================================

安装
------------

    pip3 install git+ssh://git@gitlab.zozo.cn:tech/git-py-pre-receive-hook.git

    ln -s $(which git-py-pre-receive) /home/git/repositories/my-project.git/hooks/pre-receive

检查效果：

.. class:: no-web

    .. image:: ../raw/master/screenshot.png?raw=true
        :width: 80%
        :align: left

.. class:: no-web

License
-------

The script is released under the MIT License.  The MIT License is registered
with and approved by the Open Source Initiative [1]_.

.. [1] https://opensource.org/licenses/MIT
