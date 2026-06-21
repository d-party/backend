from django.views.generic import TemplateView


class AdminChartsView(TemplateView):
    template_name = "chart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Chart"
        return context


# ランディング（IndexView）/ 使い方（UsageView）/ ルーム遷移ロビー（AnimeRoomLobby）
# は React フロントエンドへ移行した。ロビーが行っていた room_id → dアニメストアの
# リダイレクト URL 解決は REST API（api.views.AnimeStoreLobbyResolveAPI）へ移設している。
