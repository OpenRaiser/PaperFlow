param(
    [string]$UserId = "ou_c4f5d0e9c7185e943cbd4216c9b68de7",
    [string]$MessageText = "Test message"
)

# 创建飞书 post 消息内容
# 格式要求：每行是一个数组，包含一个或多个 block
$lines = $MessageText -split "`n"

$content = @()
foreach ($line in $lines) {
    if ($line.Trim()) {
        $block = @{
            tag = "text"
            text = $line
        }
        $content += @(,$block)  # 使用 , 创建嵌套数组
    }
}

$postData = @{
    zh_cn = @{
        title = "Daily Push"
        content = $content
    }
}

$jsonStr = $postData | ConvertTo-Json -Depth 10 -Compress

# 发送消息
& "$env:USERPROFILE\npm-global\lark-cli.cmd" im +messages-send --user-id $UserId --content $jsonStr --msg-type post
