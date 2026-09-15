# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/d-party/backend/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                    |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------------------------- | -------: | -------: | ------: | --------: |
| api/\_\_init\_\_.py                                     |        0 |        0 |    100% |           |
| api/apps.py                                             |        4 |        0 |    100% |           |
| api/urls.py                                             |        3 |        0 |    100% |           |
| api/views.py                                            |      194 |       36 |     81% |140-143, 156, 223-231, 243, 265, 284, 301-310, 320, 330, 343, 346, 351, 356-358, 368, 373-375, 385, 415 |
| d\_party/\_\_init\_\_.py                                |        0 |        0 |    100% |           |
| d\_party/settings.py                                    |       40 |        0 |    100% |           |
| d\_party/urls.py                                        |        7 |        0 |    100% |           |
| streamer/\_\_init\_\_.py                                |        0 |        0 |    100% |           |
| streamer/admin.py                                       |       54 |        6 |     89% |15, 20, 33, 51, 56, 61 |
| streamer/apps.py                                        |        4 |        0 |    100% |           |
| streamer/consumers.py                                   |      312 |       40 |     87% |46-54, 61, 71, 239-240, 288, 321, 342-351, 363-374, 392, 415-419, 429, 462, 535-540, 698, 725 |
| streamer/cron.py                                        |       10 |        0 |    100% |           |
| streamer/factories.py                                   |       25 |        0 |    100% |           |
| streamer/fields.py                                      |       23 |        3 |     87% |38, 43, 48 |
| streamer/format.py                                      |       55 |        1 |     98% |        79 |
| streamer/management/\_\_init\_\_.py                     |        0 |        0 |    100% |           |
| streamer/management/commands/\_\_init\_\_.py            |        0 |        0 |    100% |           |
| streamer/management/commands/close\_active\_sessions.py |       16 |        0 |    100% |           |
| streamer/mixins.py                                      |       38 |        7 |     82% |33, 36, 67, 73-74, 77, 80 |
| streamer/models.py                                      |       62 |        1 |     98% |       117 |
| streamer/util.py                                        |        7 |        2 |     71% |     27-28 |
| **TOTAL**                                               |  **854** |   **96** | **89%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/d-party/backend/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/d-party/backend/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/d-party/backend/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/d-party/backend/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fd-party%2Fbackend%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/d-party/backend/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.