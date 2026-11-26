# 入门指引

操作前需在管理端进行系统相关初始化设置（详见管理端初始化 [点击查看](https://help.dmxsmart.com/docs/printer/FunctionTerminal/ManagementInit/InitializationProcess)）

## 打单操作

创建打单

步骤：**OMS ＞运单 ＞创建打单 ＞新建 ＞填写信息 ＞ 保存草稿/下单**

![](../.gitbook/assets/images/2dca085bb9f9-1721012005993-e6521020-8b0a-45f3-a813-e66992169833.png)

下单前可进行运费试算，选择最优渠道下单

![](../.gitbook/assets/images/957df26887ab-1721699267911-d357924b-28ad-4c80-858a-1e07bdb6eee3.png)

信息填写完毕后，点击**保存到草稿**，打单将转为**草稿**状态，点击**直接下单**，打单为**已打单**状态。

可在 **OMS ＞运单 ＞打单列表 ＞已打单** 中查看。

![](../.gitbook/assets/images/040b087824de-1721103222496-bd4c8c21-6868-447d-9850-c5878b060c0a.png)

**草稿**状态下可以编辑提交打单或删除打单。

![](../.gitbook/assets/images/03ab2771424e-1721103283951-94fac076-35c4-4e6f-97c3-64c86e122662.png)

**已打单**的运单可以选择取消打单，如果管理端设置了取消规则，则需要管理端审核后取消打单。

![](../.gitbook/assets/images/14b910dd4d60-1721103534700-89479fe1-2947-4edd-9af4-119673713681.png)

等待管理端审核的取消申请在 **OMS ＞运单 ＞取消打单 **中查看进度。

![](../.gitbook/assets/images/d6526c00f32e-1721114372217-c4b9c7f2-9e40-4fc7-a2b9-822b93e7e6e6.png)

取消打单流程如下：

![](../.gitbook/assets/images/df26a3ae1374-1721027271219-435c7cdb-2bf9-4fbc-a916-7ebad18faa8d.png)

点击订单编号，可以查看此订单的基本信息、费用信息和操作记录等信息。

![](../.gitbook/assets/images/36e2ec278fc5-1721012062277-d858f3c0-48b4-417a-bdf1-43441aca9495.png)

## 查看费用详情

状态为“**已打单**”的订单可点击订单编号查看订单费用信息。

![](../.gitbook/assets/images/99ae5de93948-1721012142216-c967bf8d-3bde-4b7a-963b-505061a10b06.png)

也可在 **OMS ＞结算 ＞费用记录** 中查看费用详情、费用明细，通过关键字搜索查询每单费用信息，选中单据可一键导出多个单据的费用记录。

![](../.gitbook/assets/images/0b2750737195-1721012192580-2d08da43-6ba2-408c-ac2d-43a371c6bc73.png)

## 查看账单

在 **OMS ＞结算 ＞账单记录** 中查看账单。账单由管理端创建，客户无法对账单费用进行任何编辑、修改等操作，已生成的账单通过操作可以导出发票、账单明细等动作。

![](../.gitbook/assets/images/13965d88c4f2-1721012202459-a37ad48a-8ed2-4c5d-abfc-0e6023333621.png)

## 账户余额管理

管理端对接微信和企业支付宝账号后，余额充值可在**OMS ＞结算＞在线支付**中进行在线充值。

在 **OMS ＞结算＞充值记录**中可以查看到充值记录，客户端可创建充值记录由管理端审核充值。

![](../.gitbook/assets/images/7ed4d0e2304e-1724924600567-7256e94c-05c3-4c2c-901c-49839d69287b.png)

可下单金额=账户余额+信用额度，当可下单金额为0将无法提交单据，请管理端进行余额充值或是信用额度修改。

在 **OMS ＞结算＞余额**中可查看账户余额

![](../.gitbook/assets/images/7f5770be733e-1721630696424-4238d286-da24-41d4-978a-fd808eea1a78.png)

## API授权

在 **OMS ＞设置＞API授权码 **新建API授权码

![](../.gitbook/assets/images/c53fc10a0c24-1740449498341-d89c1f7b-1440-4e75-958b-3748f9308163.png)

![](../.gitbook/assets/images/e21c822fc85e-1740449534870-1ce4ea7b-a0a4-4ca9-bd33-b90bcc3c8dd4.png)

点击查看详情

![](../.gitbook/assets/images/a06dc84be183-1740449562725-d6df30b0-692b-433d-936d-f5a46723c468.png)

## 平台订单打单

绑定销售平台账号。选择销售平台的账户类型，录入销售平台提供的对接信息进行对接

![](../.gitbook/assets/images/1df31d505a99-1778225035993-3a273f57-b742-4c08-8c50-adec103aadd6.png)

从平台拉单，点击**拉取订单**，选择销售平台账号和时间范围，系统会自动将销售平台订单拉取到系统中

![](../.gitbook/assets/images/2e31f428f4db-1778225074549-23925370-1734-4f35-b5f7-7a5e4cd7f930.png)

对订单的产品进行申报，录入产品的长宽高重量，申报数据将用于传给服务商打单

![](../.gitbook/assets/images/439f34d37c7b-1778225281849-3e7cbd27-c188-4412-b371-845defe662e2.png)

完成申报后，对订单补充申报信息。

可以提前将店铺的所有产品录好申报信息，这样从平台拉单后，系统会自动应用申报信息，无需手动操作补充申报信息

![](../.gitbook/assets/images/6a27e0ad51a1-1778226336212-92572bc4-2eac-4fd8-bec1-16c967a7dd1a.png)

设置仓库和运送方式

![](../.gitbook/assets/images/ce4e9464a300-1778226515544-e3715b55-0e21-4b33-b042-05324eaca807.png)

生成运单

![](../.gitbook/assets/images/b0d75f5436ad-1778226530802-a3891e44-a4ef-4210-a38d-4ecea7e7296d.png)

生成运单后即打单成功，在打单列表中可查看并打印标签

![](../.gitbook/assets/images/c301ace71822-1778226592359-7cd12d3b-a151-46a2-ad92-1dc220e4dc98.png)

可配置订单自动规则，拉取平台订单后会根据条件自动配置仓库和运送方式

![](../.gitbook/assets/images/2f0025a4fbbd-1778226788867-80a327ac-c524-4bec-822e-0e8ca9fbbedf.png)

<!-- 源页面：https://help.dmxsmart.com/docs/printer/Introduction -->
