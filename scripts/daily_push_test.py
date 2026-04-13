#!/usr/bin/env python3
"""
Daily Push Test Script
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'arxiv-fetcher', 'scripts'))

from fetch_arxiv import fetch_by_date
from datetime import datetime, timedelta

def generate_daily_push(days=1, limit=50):
    # 获取日期范围
    today = datetime.now()
    end_date = today.strftime('%Y%m%d')
    start_date = (today - timedelta(days=days)).strftime('%Y%m%d')

    # 抓取论文
    papers = fetch_by_date(
        start_date=start_date,
        end_date=end_date,
        categories=['cs.AI', 'cs.LG', 'cs.CV'],
        limit=limit
    )

    if papers is None:
        papers = []

    # 用户画像关键词
    must_read_keywords = ['multimodal', 'vision-language', 'reasoning', 'vision', 'language']
    high_relevant_keywords = ['learning', 'neural', 'deep', 'agent', 'rl', 'reinforcement']

    # 分类
    must_read = []
    high_relevant = []
    maybe_interested = []

    def match_keywords(paper, keywords):
        title = paper['title'].lower()
        for kw in keywords:
            if kw.lower() in title:
                return True
        return False

    for paper in papers:
        if match_keywords(paper, must_read_keywords):
            must_read.append(paper)
        elif match_keywords(paper, high_relevant_keywords):
            high_relevant.append(paper)
        else:
            maybe_interested.append(paper)

    # 生成推送卡片
    output = []
    output.append('=' * 60)
    output.append('[Daily Push] {}'.format(end_date))
    output.append('=' * 60)
    output.append('Date range: {} to {}'.format(start_date, end_date))
    output.append('Total: {} papers -> Filtered: {} papers'.format(len(papers), len(papers)))
    output.append('')

    if must_read:
        output.append('--- MUST READ ({} papers) ---'.format(len(must_read)))
        for i, p in enumerate(must_read[:10]):
            output.append('  {:02d}. {}: {}'.format(i+1, p['arxiv_id'], p['title'][:55]))
        output.append('')

    if high_relevant:
        output.append('--- HIGH RELEVANT ({} papers) ---'.format(len(high_relevant)))
        for i, p in enumerate(high_relevant[:10]):
            output.append('  {:02d}. {}: {}'.format(i+1, p['arxiv_id'], p['title'][:55]))
        output.append('')

    if maybe_interested:
        output.append('--- MAYBE INTERESTED ({} papers) ---'.format(len(maybe_interested)))
        for i, p in enumerate(maybe_interested[:15]):
            output.append('  {:02d}. {}: {}'.format(i+1, p['arxiv_id'], p['title'][:55]))
        output.append('')

    output.append('Reply with numbers to select: 1 2 4 6 7 9 11')
    output.append('Or: all lock | all red | none')

    return '\n'.join(output)

if __name__ == '__main__':
    result = generate_daily_push(days=1, limit=50)
    # 输出到文件避免控制台编码问题
    with open('daily_push_output.txt', 'w', encoding='utf-8') as f:
        f.write(result)
    print("Output written to daily_push_output.txt")
    # 打印前 20 行到控制台
    for line in result.split('\n')[:25]:
        try:
            print(line)
        except:
            pass
