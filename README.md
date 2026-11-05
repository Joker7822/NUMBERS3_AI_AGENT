# NUMBERS3 AI AGENT

ナンバーズ3専用のオンライン照合・2時間ごとの研究用学習・研究方法探索・公開ダッシュボード。

## 対応状況

| 機能 | 状態 |
|---|---|
| 3桁数字・先頭ゼロの保持 | 対応 |
| ストレート・ボックス・セット・ミニ | 対応 |
| みずほ銀行と楽天の独立照合 | 対応。両方一致した回のみ正式な結果 |
| 楽天のみの結果 | 研究資料として保存。正式採点不可 |
| 過去結果だけで時系列の研究予測・照合 | 対応。予測力の証明ではない |
| Crossrefによる学術研究の探索 | 対応。検索した外部コードは実行しない |
| GitHub Actions 2時間おき | 対応。00, 02, …, 22時 JST |
| 直近7日間の研究用予測ダッシュボード | 対応 |
| 実際の事前公開証拠に基づく正式成績 | 未確立。未検証の記録は採点しない |
| 本番モデルの統計検証付き自動昇格 | 未実装 |
| 宝くじの自動購入 | 非対応 |

## Numbers3の公式ルール

3桁完全一致のストレートは理論確率1/1,000。ボックスは桁順を問わず、セットはストレートとボックスの組合せです。3桁すべて同じ数字でボックス／セットは申し込めません。ミニは下2桁の順序一致、理論確率1/100。1口200円。

公式ルール出典：https://www.takarakuji-official.jp/brand/suji/lineup-numbers3/

## 実行方法

Python 3.12以上。基本エンジンは標準ライブラリだけで動作します。

- テスト： python -m unittest discover -s tests -v
- 取得： python -m numbers3_agent.cli --root . fetch --months-back 3
- 研究再現： python -m numbers3_agent.cli --root . replay
- 公開画面作成： python -m numbers3_agent.cli --root . dashboard
- 全実行： python -m numbers3_agent.cli --root . cycle --months-back 3

銀行のJavaScript画面を表示するオプションは --bank-browser-fallback。GitHubの自動実行ではPlaywrightとChromiumをインストールします。

## 自動更新・監査

自動実行設定は .github/workflows/online-learning.yml です。cronはUTCで 0 1-23/2 * * *。毎日00,02,04,…22時 JSTに相当し、GitHub Actionsの遅延・スキップがあり得ます。初回は直近12ヶ月、次からは直近3ヶ月の結果取得を試みます。

- data/verified_draws.json：銀行＋楽天の回号・日付・数字が一致した結果のみ。
- data/secondary_history.json：楽天のみの参考履歴。銀行公式未照合。
- data/secondary_extended.json：Numbers3専用V2の全履歴を楽天との重複区間で照合した研究用データ。これは銀行公式照合ではありません。
- research/historical_extension_audit.json：全履歴取り込み時の楽天重複回数、入力のSHA-256、失敗状態。
- research/replay.json：前の回までの情報だけで再予測する研究レポート。
- research/round_predictions.csv：研究用逐次予測・実結果の回別記録。
- research/academic_discovery.json：安全に取得した学術論文のDOI・題名。
- docs/data/status.json：ダッシュボードの公開データ。
- data/issued_forecasts.jsonl：明示的に事前発行した予測記録。独立したGitHubのサーバー時刻の確認機能は未実装のため、正式採点に流用しません。

ダッシュボードは docs/index.html 。新規リポジトリでは **Settings → Pages → Build and deployment → Source を GitHub Actions に設定**する必要があります。設定前はデプロイを安全にスキップし、サイトが公開されたと誤認しません。設定後は次のコード更新・定期学習完了・手動ワークフロー実行のいずれかで公開されます。

一次公表元：https://www.mizuhobank.co.jp/takarakuji/check/numbers/numbers3/index.html

二次公表元：https://takarakuji.rakuten.co.jp/backnumber/numbers3_past/

Numbers3全履歴の第三者APIは https://hazimekom.github.io/numbers4-api/api/v2/games/numbers3/draws.min.json です。リポジトリ名に Numbers4 が含まれていますが、利用するエンドポイントは **Numbers3専用V2** です。楽天との重複期間の回号・日付・結果が一致した場合に限り、第1回からの研究用再予測に使います。2つの二次公開元が同じ一次情報を利用している可能性を排除できないため、正式な独立照合には昇格しません。

**Numbers4の結果、4桁番号、過去の的中実績は一切流用していません。** 過去データに対する研究比較は将来の有意な予測力を証明しません。購入、収益、モデル自動昇格の主張は行いません。
