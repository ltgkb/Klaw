# Elasticsearch 8.11.0 + IK 中文分词插件
FROM docker.elastic.co/elasticsearch/elasticsearch:8.11.0

# 安装 analysis-ik 8.11.0
RUN elasticsearch-plugin install --batch \
    https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.11.0.zip
