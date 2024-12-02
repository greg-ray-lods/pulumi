import pulumi
from pulumi_azure_native import resources, storage, network, compute, sql

# Use Pulumi Config to manage configurations and secrets securely
config = pulumi.Config()

# Get the Azure location from configuration (defaults to 'EastUS' if not set)
location = config.get("azure-native:location") or "EastUS"

# Get VM admin credentials from config
admin_username = config.get("adminUsername") or "azureuser"
admin_password = config.require_secret("adminPassword")

# Get SQL admin credentials and server name from config
sql_admin_username = config.get("sqlAdminUsername") or "sqladminuser"
sql_admin_password = config.require_secret("sqlAdminPassword")

# Get SQL server name from config (must be globally unique)
sql_server_name = config.require("sqlServerName")

# Create an Azure Resource Group
resource_group = resources.ResourceGroup(
    "resource_group",
    location=location
)

# Create an Azure Storage Account
account = storage.StorageAccount(
    "sa",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=storage.SkuArgs(
        name=storage.SkuName.STANDARD_LRS,
    ),
    kind=storage.Kind.STORAGE_V2,
)

# Enable static website support
static_website = storage.StorageAccountStaticWebsite(
    "staticWebsite",
    account_name=account.name,
    resource_group_name=resource_group.name,
    index_document="index.html",
)

# Upload the index.html file
index_html = storage.Blob(
    "index.html",
    resource_group_name=resource_group.name,
    account_name=account.name,
    container_name="$web",
    source=pulumi.FileAsset("index.html"),
    content_type="text/html",
)

# Export the primary key of the Storage Account (as a secret)
primary_key = pulumi.Output.all(resource_group.name, account.name).apply(
    lambda args: storage.list_storage_account_keys(
        resource_group_name=args[0],
        account_name=args[1],
    )
).apply(lambda account_keys: account_keys.keys[0].value)

pulumi.export("primary_storage_key", pulumi.Output.secret(primary_key))

# Web endpoint to the website
pulumi.export("staticEndpoint", account.primary_endpoints.web)

# Create a Virtual Network (VNet)
vnet = network.VirtualNetwork(
    "myVNet",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    address_space=network.AddressSpaceArgs(
        address_prefixes=["10.0.0.0/16"],
    ),
)

# Create a Subnet within the VNet
subnet = network.Subnet(
    "mySubnet",
    resource_group_name=resource_group.name,
    virtual_network_name=vnet.name,
    address_prefix="10.0.1.0/24",
)

# Create a Network Interface connected to the Subnet
nic = network.NetworkInterface(
    "myNIC",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    ip_configurations=[
        network.NetworkInterfaceIPConfigurationArgs(
            name="ipconfig1",
            subnet=network.SubnetArgs(
                id=subnet.id,
            ),
            private_ip_allocation_method=network.IPAllocationMethod.DYNAMIC,
        )
    ],
)

# Create a Virtual Machine
vm = compute.VirtualMachine(
    "myVM",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    network_profile=compute.NetworkProfileArgs(
        network_interfaces=[
            compute.NetworkInterfaceReferenceArgs(
                id=nic.id,
                primary=True,
            )
        ],
    ),
    hardware_profile=compute.HardwareProfileArgs(
        vm_size="Standard_DS1_v2",
    ),
    os_profile=compute.OSProfileArgs(
        computer_name="myvm",
        admin_username=admin_username,
        admin_password=admin_password,
    ),
    storage_profile=compute.StorageProfileArgs(
        image_reference=compute.ImageReferenceArgs(
            publisher="Canonical",
            offer="UbuntuServer",
            sku="18.04-LTS",
            version="latest",
        ),
        os_disk=compute.OSDiskArgs(
            name="myOSDisk",
            caching=compute.CachingTypes.READ_WRITE,
            create_option=compute.DiskCreateOptionTypes.FROM_IMAGE,
            managed_disk=compute.ManagedDiskParametersArgs(
                storage_account_type=compute.StorageAccountTypes.STANDARD_LRS,
            ),
        ),
    ),
)

# Export the VM's ID
pulumi.export("vm_id", vm.id)

# Create an Azure SQL Server
sql_server = sql.Server(
    "mySqlServer",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    server_name=sql_server_name,
    administrator_login=sql_admin_username,
    administrator_login_password=sql_admin_password,
    version="12.0",  # Latest version
    public_network_access="Enabled",
)

# Create an Azure SQL Database
sql_database = sql.Database(
    "mySqlDatabase",
    resource_group_name=resource_group.name,
    server_name=sql_server.name,
    sku=sql.SkuArgs(
        name="S0",
        tier="Standard",
    ),
)

# Export the SQL Database connection string (as a secret)
connection_string = pulumi.Output.all(
    sql_server.name, sql_database.name, sql_admin_username, sql_admin_password
).apply(
    lambda args: f"Server=tcp:{args[0]}.database.windows.net;Database={args[1]};User ID={args[2]};Password={args[3]};Encrypt=true;Connection Timeout=30;"
)

pulumi.export("sql_connection_string", pulumi.Output.secret(connection_string))
