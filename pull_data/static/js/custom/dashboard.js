(function () {
    "use strict";

    /* Form Submit Listing Chart */
    const chartEl = document.getElementById('form_submit_listing_chart');
    if (!chartEl) return;

    const apiUrl  = chartEl.dataset.apiUrl;
    const eventId = chartEl.dataset.eventId;

    let chartInstance = null;

    function buildChartOptions(formStats) {
        const names     = formStats.map(function(f){ return f.form_name; });
        const submitted = formStats.map(function(f){ return f.submitted; });

        return {
            series: [
                { name: 'Total Submitted', data: submitted }
            ],
            chart: {
                height: 457,
                type: 'bar',
                toolbar: { show: false }
            },
            colors: ['#00cae3'],
            plotOptions: {
                bar: {
                    horizontal: true,
                    barHeight: '55%',
                    distributed: true,
                    borderRadius: 6,
                    borderRadiusApplication: 'end',
                }
            },
            dataLabels: { enabled: false },
            legend: { show: false },
            grid: {
                strokeDashArray: 0,
                borderColor: '#E0E0E0',
            },
            xaxis: {
                categories: names,
                axisBorder: { show: true, color: '#E0E0E0' },
                axisTicks:  { show: true, color: '#E0E0E0' },
                labels: {
                    show: true,
                    style: {
                        colors: '#919aa3',
                        fontSize: '12px',
                        fontFamily: 'Outfit',
                    },
                    formatter: function(val) { return Math.floor(val); }
                },
                min: 0,
                forceNiceScale: true,
            },
            yaxis: {
                labels: {
                    show: true,
                    style: {
                        colors: '#919aa3',
                        fontSize: '13px',
                        fontFamily: 'Outfit',
                    },
                    maxWidth: 280,
                }
            },
            tooltip: {
                y: {
                    formatter: function(val) { return val + ' submitted'; }
                }
            },
            noData: {
                text: 'No form data for this event.',
                style: { color: '#919aa3', fontSize: '14px', fontFamily: 'Outfit' }
            }
        };
    }

    function loadChart(evId) {
        var url = apiUrl + (evId ? '?event_id=' + evId : '');
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function(r){ return r.json(); })
            .then(function(data) {
                var opts = buildChartOptions(data.form_stats || []);
                if (chartInstance) {
                    chartInstance.updateOptions(opts, true, true);
                } else {
                    chartInstance = new ApexCharts(chartEl, opts);
                    chartInstance.render();
                }
            })
            .catch(function(err) { console.error('Form submit chart error:', err); });
    }

    loadChart(eventId);
    window.loadFormSubmitChart = loadChart;
})();
