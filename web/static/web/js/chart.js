axios.get('/api/v1/statistics/anime-store/active-user-per-day')
  .then(function (response) {
    let xdata_user=[];
    let ydata_user=[];
    response.data.data.forEach(element => {xdata_user.push(element.day);ydata_user.push(element.count);});
    var chartDom = document.getElementById('active_user');
    var myChart = echarts.init(chartDom,"dark");
    var option;
    
    option = {
        title: {
            text: '1日ごとのユーザー数'
          },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          }
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
      xAxis: {
        type: 'category',
        data: xdata_user,
        axisTick: {
          alignWithLabel: true
        }
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name:"ユーザー数",
          data: ydata_user,
          type: 'bar'
        }
      ]
    };
    
    myChart.setOption(option);
});


axios.get('/api/v1/statistics/anime-store/active-room-per-day')
  .then(function (response) {
    let xdata_room=[];
    let ydata_room=[];
    response.data.data.forEach(element => {xdata_room.push(element.day);ydata_room.push(element.count);});
    var chartDom = document.getElementById('active_room');
    var myChart = echarts.init(chartDom,"dark");
    var option;
    
    option = {
        title: {
            text: '1日ごとのルーム数'
          },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          }
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
      xAxis: {
        type: 'category',
        data: xdata_room,
        axisTick: {
          alignWithLabel: true
        }
      },
      yAxis: {
        type: 'value',
      },
      series: [
        {
          name:"ルーム数",
          data: ydata_room,
          type: 'bar'
        }
      ]
    };
    
    myChart.setOption(option);
})

axios.get('/api/v1/statistics/anime-store/anime-reaction-count')
  .then(function (response) {
    let xdata_reaction=[];
    let ydata_reaction=[];
    response.data.data.forEach(element => {xdata_reaction.push(element.reaction_type);ydata_reaction.push(element.count);});
    var chartDom = document.getElementById('reaction_room');
    var myChart = echarts.init(chartDom,"dark");
    var option;
    
    option = {
        title: {
            text: 'リアクションの総数'
          },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          }
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
      xAxis: {
        type: 'category',
        data: xdata_reaction,
        axisTick: {
          alignWithLabel: true
        }
      },
      yAxis: {
        type: 'value'
      },
      series: [
        {
          name:"リアクション数",
          data: ydata_reaction,
          type: 'bar'
        }
      ]
    };
    
    myChart.setOption(option);
})

axios.get('/api/v1/statistics/anime-store/anime-user-alive-count')
  .then(function (response) {
    document.getElementById("alive-user").innerText=response.data.data.count;
});
axios.get('/api/v1/statistics/anime-store/anime-room-alive-count')
  .then(function (response) {
    document.getElementById("alive-room").innerText=response.data.data.count;
});

axios.get('/api/v1/statistics/anime-store/anime-user-all-count')
  .then(function (response) {
    document.getElementById("all-user").innerText=response.data.data.count;
});

axios.get('/api/v1/statistics/anime-store/anime-room-all-count')
  .then(function (response) {
    document.getElementById("all-room").innerText=response.data.data.count;
});

axios.get('/api/v1/statistics/anime-store/anime-reaction-all-count')
  .then(function (response) {
    document.getElementById("all-reaction").innerText=response.data.data.count;
});