# Как залить это в GitHub Wiki

GitHub Wiki это отдельный git-репозиторий: `<repo>.wiki.git`.

Этот каталог (`docs/wiki/`) сделан в формате "один файл = одна wiki-страница", чтобы было просто синкать.

## Публикация вручную

Из корня репозитория:

```bash
WIKI_URL="$(git remote get-url origin | sed 's/\.git$/.wiki.git/')"
rm -rf /tmp/project.wiki
git clone "$WIKI_URL" /tmp/project.wiki
rsync -av --delete docs/wiki/ /tmp/project.wiki/
cd /tmp/project.wiki
git add -A
git commit -m "Update Roistat docs" || true
git push
```

Если удобнее, можно просто скопировать содержимое страниц в Wiki через веб-интерфейс.
